# -*- coding: utf-8 -*-
"""识别路由 —— D8 §6 recognize 组（2 个端点）

  POST /api/recognize         单张识别
  POST /api/recognize/batch   批量识别（顺序执行，PRD FR-RECOG-05）

【额度口径】游客额度【在本端点成功后扣减】。
前置检查用 enforce_guest_quota（不足 → 42901），成功后 consume_guest_quota。

【为什么上传不扣、这里才扣】PRD 决策基线：上传只是缓存图片，
用户可能上传后不识别；若上传即扣，会造成额度无谓消耗。

【批量识别的额度与失败语义（关键设计）】
  · 顺序执行，非并发 —— 模型单实例 + 8GB 显存，并发会 OOM；
    且 PRD §9 要求端到端 ≤3s/图，顺序执行时长可预期。
  · 逐张扣额度：每张成功后扣 1 次。游客额度在批次中途耗尽时，
    已成功的张数保留，剩余张数返回 42901 —— 不做整批回滚，
    因为已消耗的算力无法退回，且用户能看到部分结果优于全失败。
  · 单张失败不中断整批：该项记 error 后继续下一张，最终在
    results 里逐项给出状态。这与"批量上传"的尽力而为语义一致。
  · 全批失败时 HTTP 仍为 200，由每项的 code 表达结果 ——
    避免前端把"部分成功"误判为整体失败。
"""

import os
import sys

from fastapi import APIRouter, Depends

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.dependencies import (            # noqa: E402
    RATE_LIMIT_DEP, DbSession, GuestSession, OptionalUser,
    assert_can_access, consume_guest_quota, enforce_guest_quota,
    guest_quota_state,
)
from app.core.errors import (                                   # noqa: E402
    ERROR_TABLE, BizError, E_40101, E_40401, E_42901, ok,
)
from app.models import ImageAsset                            # noqa: E402
from app.schemas import (                                     # noqa: E402
    BatchRecognizeIn, ImageOut, RecognizeIn, RecognizeOut,
)
from app.services import image_service, record_service        # noqa: E402
from app.services.inference import engine                     # noqa: E402
from app.services.user_service import log_action              # noqa: E402

router = APIRouter(tags=['recognize'])


def _do_recognize(body: RecognizeIn, db, user, guest) -> dict:
    """单张识别的完整流程。供单张端点与批量端点共用。

    顺序（关键，勿调整）：
      1. 解析图片并做归属校验（未授权 → 40401）
      2. 游客额度前置检查（不足 → 42901）
      3. 推理（模型未加载 → 50301；队列满 → 50302；解码失败 → 42201）
      4. 登录用户落库；游客【不落库】（D7 §2.2：游客结果不落库）
      5. 游客扣减额度
    """
    ast = db.get(ImageAsset, body.image_id)
    if ast is None:
        raise BizError(E_40401)

    # 1) 归属：有 owner 的图必须本人/管理员；无 owner 的游客图凭 UUID 可读
    if ast.user_id is not None:
        assert_can_access(ast.user_id, user, guest)
    else:
        if user is None and not guest:
            raise BizError(E_40101)

    # 2) 额度前置检查（仅游客）
    if user is None:
        enforce_guest_quota(db, guest)

    # 3) 推理
    raw = image_service.read_bytes(ast)
    prediction = engine.predict(raw, top_k=body.top_k)

    # 4) 落库（仅登录用户）
    record_id = None
    species_out = None
    smap = record_service.load_species_map(db)
    sp = smap.get(prediction['class_index'])
    if sp is not None:
        species_out = {
            'class_index': sp.class_index,
            'cn_name': sp.cn_name,
            'latin_name': sp.latin_name,
            'common_name': sp.common_name,
            'morphology': sp.morphology,
            'habit': sp.habit,
            'distribution': sp.distribution,
            'image_path': sp.image_path,
        }

    if user is not None:
        rec = record_service.save_record(
            db, user_id=user.id, image_id=ast.id,
            prediction=prediction, species_rows=smap, top_k=body.top_k)
        record_id = rec.id
        log_action(db, action='recognize', user=user, target_type='record',
                   target_id=rec.id,
                   detail=f'识别 {ast.original_filename} → {prediction["cn_name"]} '
                          f'({prediction["confidence"]:.3f})')

    # 5) 游客扣额度
    quota = None
    if user is None:
        quota = consume_guest_quota(db, guest)

    is_low = prediction['confidence'] < record_service.LOW_CONFIDENCE_THRESHOLD
    return {
        'record_id': record_id,
        'image': ImageOut.model_validate(ast).model_dump(),
        'class_index': prediction['class_index'],
        'cn_name': prediction['cn_name'],
        'latin_name': prediction['latin_name'],
        'confidence': prediction['confidence'],
        'is_low_confidence': is_low,
        'candidates': [
            {'rank': c['rank'], 'class_index': c['class_index'],
             'cn_name': c['cn_name'], 'latin_name': c['latin_name'],
             'confidence': c['confidence']}
            for c in prediction['candidates']
        ],
        'species': species_out,
        'duration_ms': prediction['inference_ms'],
        'model_version': prediction['model_version'],
        'guest_quota': quota,
    }


@router.post('/recognize', dependencies=RATE_LIMIT_DEP)
def recognize(body: RecognizeIn, db: DbSession,
              user: OptionalUser, guest: GuestSession):
    """执行一次识别。"""
    data = _do_recognize(body, db, user, guest)
    db.commit()
    return ok(data, '识别完成')


@router.post('/recognize/batch', dependencies=RATE_LIMIT_DEP)
def recognize_batch(body: BatchRecognizeIn, db: DbSession,
                    user: OptionalUser, guest: GuestSession):
    """批量识别（顺序执行）。

    详见模块 docstring 的「批量识别的额度与失败语义」。
    """
    results = []
    for img_id in body.image_ids:
        try:
            data = _do_recognize(
                RecognizeIn(image_id=img_id, top_k=body.top_k),
                db, user, guest)
            results.append({'image_id': img_id, 'code': 0, 'message': 'ok',
                            'data': data})
        except BizError as e:
            # 单张失败不中断整批；db 可能有未提交的脏状态 → 回滚后继续
            db.rollback()
            results.append({
                'image_id': img_id, 'code': e.code, 'message': e.message,
                'data': None,
            })
            # 额度耗尽后无需继续（后续必然同样失败），提前结束
            if e.code == E_42901:
                break

    db.commit()

    succeeded = sum(1 for r in results if r['code'] == 0)
    quota = guest_quota_state(db, guest) if user is None else None
    return ok({
        'total': len(body.image_ids),
        'processed': len(results),
        'succeeded': succeeded,
        'failed': len(results) - succeeded,
        'results': results,
        'guest_quota': quota,
    }, f'批量识别完成：成功 {succeeded}/{len(results)}')
