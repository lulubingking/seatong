# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 识别记录服务

职责：
  · 识别结果落库（candidates_json 的写入与自校验 —— D7 §8.2 C-07）
  · 历史记录列表 / 详情 / 软删除 / 导出 CSV
  · 统计聚合

【D7 §8.2 C-07 要求】candidates_json 内的 class_index 与 species 表的
对应关系不受数据库约束保护，必须由写入侧保证。本模块提供
`validate_candidates()` 在写入前逐项校验，并提供全量扫描函数供联调核对。

【软删除】recognition_record 用 is_deleted + deleted_at，
不做物理删除（保留审计可追溯性）。
"""

import csv
import io
import json
import os
import sys
import time
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.config import settings                      # noqa: E402
from app.core.errors import BizError, E_40001, E_40401     # noqa: E402
from app.models import ImageAsset, RecognitionRecord, SpeciesModel  # noqa: E402
from app.services.user_service import log_action           # noqa: E402

# 低置信度阈值（PRD 决策基线：低于此值前端提示"结果仅供参考"）
LOW_CONFIDENCE_THRESHOLD = 0.60

# 候选数上限
TOP_K = 5


# ---------------- candidates_json 写入 ----------------

def build_candidates(prediction: dict, species_rows: dict[int, SpeciesModel],
                     top_k: int = TOP_K) -> list[dict]:
    """构造 candidates_json 的内容。

    【决策 2】冗余存 cn_name —— 服务于 BR-HISTORY-09 结果恒定性：
    物种知识库日后改名，历史记录仍应展示识别当时的中文名。
    同时存 species_id 用于按物种筛选的联表。

    结构：
      [{"rank":1, "class_index":0, "species_id":1,
        "cn_name":"网纹宅泥鱼", "latin_name":"Dascyllus reticulatus",
        "confidence":0.98}, ...]
    """
    out = []
    for c in prediction['candidates'][:top_k]:
        ci = int(c['class_index'])
        sp = species_rows.get(ci)
        out.append({
            'rank': int(c['rank']),
            'class_index': ci,
            'species_id': sp.id if sp else None,
            'cn_name': c['cn_name'],
            'latin_name': c['latin_name'],
            'confidence': round(float(c['confidence']), 6),
        })
    return out


def validate_candidates(cands: list[dict],
                        species_rows: dict[int, SpeciesModel]) -> list[str]:
    """写入前校验（D7 §8.2 C-07）。返回问题清单，空 = 通过。

    校验三项：
      1. class_index 落在 0～22
      2. species_id 与 class_index 的对应关系与 species 表一致
      3. rank 从 1 连续递增，confidence 单调不增
    """
    problems = []
    if not cands:
        problems.append('candidates 为空')
        return problems
    if len(cands) > TOP_K:
        problems.append(f'候选数 {len(cands)} 超过 {TOP_K}')

    ranks = [c['rank'] for c in cands]
    if ranks != list(range(1, len(cands) + 1)):
        problems.append(f'rank 非连续递增: {ranks}')

    confs = [c['confidence'] for c in cands]
    if any(confs[i] < confs[i + 1] - 1e-9 for i in range(len(confs) - 1)):
        problems.append(f'confidence 非单调不增: {confs}')

    for c in cands:
        ci = c.get('class_index')
        if not isinstance(ci, int) or not (0 <= ci <= 22):
            problems.append(f'class_index 越界: {ci}')
            continue
        sp = species_rows.get(ci)
        if sp is None:
            problems.append(f'class_index={ci} 在 species 表中不存在')
            continue
        if c.get('species_id') != sp.id:
            problems.append(
                f'class_index={ci} 的 species_id 错位：'
                f'candidates 存 {c.get("species_id")}，species 表为 {sp.id}')
        if c.get('cn_name') != sp.cn_name:
            problems.append(
                f'class_index={ci} 的 cn_name 不一致：'
                f'candidates 存 {c.get("cn_name")!r}，species 表为 {sp.cn_name!r}')
    return problems


def scan_all_candidates(db: Session) -> dict:
    """全量扫描既有数据（D7 §8.2 C-07 的联调检查项）。"""
    species_rows = load_species_map(db)
    total = bad = 0
    details = []
    for rec in db.scalars(select(RecognitionRecord)):
        total += 1
        try:
            cands = json.loads(rec.candidates_json)
        except Exception as e:
            bad += 1
            details.append(f'{rec.id}: JSON 解析失败 {e}')
            continue
        probs = validate_candidates(cands, species_rows)
        if probs:
            bad += 1
            details.append(f'{rec.id}: ' + '; '.join(probs))
    return {'total': total, 'bad': bad, 'details': details}


# ---------------- 物种映射 ----------------

def load_species_map(db: Session) -> dict[int, SpeciesModel]:
    """class_index → SpeciesModel。这是三处对齐的唯一键（D7 决策 3）。"""
    return {s.class_index: s for s in db.scalars(select(SpeciesModel))}


# ---------------- 落库 ----------------

def save_record(db: Session, *, user_id: int, image_id: str,
                prediction: dict, species_rows: dict[int, SpeciesModel],
                top_k: int = TOP_K) -> RecognitionRecord:
    """保存一条识别记录。

    写入前执行 validate_candidates；校验不通过视为服务端缺陷，
    直接抛错而非写入脏数据 —— 脏数据的后果是历史页展示错误物种名，
    且不报错、难以察觉（D7 §8.2 明确警示）。
    """
    cands = build_candidates(prediction, species_rows, top_k)
    problems = validate_candidates(cands, species_rows)
    if problems:
        raise BizError(50001, '候选结构自校验失败（服务端缺陷）：' + '; '.join(problems))

    ci = int(prediction['class_index'])
    top1 = species_rows.get(ci)
    if top1 is None:
        raise BizError(50001, f'Top-1 class_index={ci} 不在 species 表中')

    now = int(time.time())
    rec = RecognitionRecord(
        id=str(uuid.uuid4()),
        user_id=user_id,
        image_id=image_id,
        top1_species_id=top1.id,
        top1_confidence=round(float(prediction['confidence']), 6),
        is_low_confidence=1 if prediction['confidence'] < LOW_CONFIDENCE_THRESHOLD else 0,
        candidates_json=json.dumps(cands, ensure_ascii=False),
        model_version=prediction['model_version'],
        duration_ms=int(prediction['inference_ms']),
        status='success',
        is_deleted=0,
        deleted_at=None,
        created_at=now,
    )
    db.add(rec)
    db.flush()
    return rec


# ---------------- 查询 ----------------

def record_to_dict(rec: RecognitionRecord, sp: SpeciesModel | None) -> dict:
    return {
        'id': rec.id,
        'class_index': sp.class_index if sp else -1,
        'cn_name': sp.cn_name if sp else '未知',
        'latin_name': sp.latin_name if sp else '',
        'confidence': rec.top1_confidence,
        'is_low_confidence': bool(rec.is_low_confidence),
        'duration_ms': rec.duration_ms,
        'status': rec.status,
        'created_at': rec.created_at,
        'image_id': rec.image_id,
        'thumb_url': f'/api/images/{rec.image_id}/thumb',
    }


def list_records(db: Session, *, user_id: int | None, page: int = 1, page_size: int = 20,
                 class_index: int | None = None,
                 start_ts: int | None = None, end_ts: int | None = None,
                 keyword: str | None = None,
                 all_users: bool = False) -> tuple[list[dict], int]:
    """历史列表。默认排除软删除。

    索引命中（D7 §4.2）：
      · idx_record_user_created (user_id, created_at DESC) —— 主查询路径
      · idx_record_species (top1_species_id) —— 按物种筛选时
    注意：筛选物种时传入的若是 class_index，需先转 species.id。

    【all_users】管理端跨用户视图（PRD FR-USER-08）置 True：
    此时 user_id 退化为可选过滤器（None = 全部用户）。
    普通历史列表置 False，user_id 为必填的归属约束。
    """
    base = select(RecognitionRecord).where(RecognitionRecord.is_deleted == 0)
    cnt = select(func.count()).select_from(RecognitionRecord).where(
        RecognitionRecord.is_deleted == 0)

    if not all_users:
        base = base.where(RecognitionRecord.user_id == user_id)
        cnt = cnt.where(RecognitionRecord.user_id == user_id)
    elif user_id is not None:
        base = base.where(RecognitionRecord.user_id == user_id)
        cnt = cnt.where(RecognitionRecord.user_id == user_id)

    if class_index is not None:
        sp = db.scalar(select(SpeciesModel).where(SpeciesModel.class_index == class_index))
        sid = sp.id if sp else -1
        base = base.where(RecognitionRecord.top1_species_id == sid)
        cnt = cnt.where(RecognitionRecord.top1_species_id == sid)
    if start_ts is not None:
        base = base.where(RecognitionRecord.created_at >= start_ts)
        cnt = cnt.where(RecognitionRecord.created_at >= start_ts)
    if end_ts is not None:
        base = base.where(RecognitionRecord.created_at <= end_ts)
        cnt = cnt.where(RecognitionRecord.created_at <= end_ts)

    total = db.scalar(cnt) or 0
    rows = db.scalars(base.order_by(RecognitionRecord.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()

    smap = {s.id: s for s in db.scalars(select(SpeciesModel))}
    items = [record_to_dict(r, smap.get(r.top1_species_id)) for r in rows]

    if keyword:
        kw = keyword.lower()
        items = [i for i in items
                 if kw in i['cn_name'].lower() or kw in i['latin_name'].lower()]
    return items, total


def get_record(db: Session, record_id: str, *, user_id: int | None,
               is_admin: bool = False) -> RecognitionRecord | None:
    """取记录并做归属校验。非本人且非管理员 → 由调用方转 40401。"""
    rec = db.get(RecognitionRecord, record_id)
    if rec is None or rec.is_deleted:
        return None
    if is_admin:
        return rec
    if user_id is None or rec.user_id != user_id:
        return None
    return rec


def record_detail(db: Session, rec: RecognitionRecord) -> dict:
    smap = load_species_map(db)
    sp = db.get(SpeciesModel, rec.top1_species_id)
    img = db.get(ImageAsset, rec.image_id)
    try:
        cands = json.loads(rec.candidates_json)
    except Exception:
        cands = []
    return {
        'record': record_to_dict(rec, sp),
        'candidates': [
            {
                'rank': c.get('rank'),
                'class_index': c.get('class_index'),
                'cn_name': c.get('cn_name'),
                'latin_name': c.get('latin_name'),
                'confidence': c.get('confidence'),
            } for c in cands
        ],
        'species': {
            'class_index': sp.class_index,
            'cn_name': sp.cn_name,
            'latin_name': sp.latin_name,
            'common_name': sp.common_name,
            'morphology': sp.morphology,
            'habit': sp.habit,
            'distribution': sp.distribution,
            'image_path': sp.image_path,
        } if sp else None,
        'image': {
            'id': img.id,
            'original_filename': img.original_filename,
            'mime_type': img.mime_type,
            'file_size': img.file_size,
            'width': img.width,
            'height': img.height,
            'content_hash': img.content_hash,
            'created_at': img.created_at,
            'expires_at': img.expires_at,
        } if img else None,
    }


def soft_delete(db: Session, *, user_id: int, record_ids: list[str],
                is_admin: bool = False, ip: str | None = None,
                actor=None) -> int:
    """批量软删除。返回实际删除条数。

    使用 is_deleted + deleted_at（D7 设计），不物理删除。
    deleted_at 供"满 30 天清理任务"使用（idx_record_deleted 索引服务）。
    """
    if not record_ids:
        raise BizError(E_40001, '未提供要删除的记录 ID')
    now = int(time.time())
    stmt = select(RecognitionRecord).where(RecognitionRecord.id.in_(record_ids))
    if not is_admin:
        stmt = stmt.where(RecognitionRecord.user_id == user_id)
    rows = db.scalars(stmt).all()
    n = 0
    for r in rows:
        if r.is_deleted:
            continue
        r.is_deleted = 1
        r.deleted_at = now
        n += 1
    db.flush()
    if n and actor is not None:
        log_action(db, action='delete', user=actor, target_type='record',
                   ip=ip, detail=f'删除 {n} 条识别记录')
    return n


# ---------------- 导出 ----------------

CSV_HEADER = ['记录ID', '识别时间', '中文名', '拉丁学名', '置信度',
              '是否低置信', '耗时(ms)', '模型版本', 'Top5候选']


def export_csv(db: Session, records: list[dict]) -> bytes:
    """导出为 CSV 字节流。

    【编码选择】用 utf-8-sig（带 BOM）—— 否则 Excel 打开中文会乱码。
    这是实际交付中最常见的问题，故默认加 BOM。
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADER)
    for r in records:
        w.writerow([
            r['id'],
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r['created_at'])),
            r['cn_name'],
            r['latin_name'],
            f"{r['confidence']:.4f}",
            '是' if r['is_low_confidence'] else '否',
            r['duration_ms'],
            r.get('model_version', ''),
            r.get('candidates_text', ''),
        ])
    return buf.getvalue().encode('utf-8-sig')


def collect_for_export(db: Session, *, user_id: int,
                       class_index: int | None = None,
                       start_ts: int | None = None,
                       end_ts: int | None = None) -> list[dict]:
    """取全部符合条件的记录用于导出（不分页）。"""
    stmt = select(RecognitionRecord).where(
        RecognitionRecord.user_id == user_id,
        RecognitionRecord.is_deleted == 0,
    )
    if class_index is not None:
        sp = db.scalar(select(SpeciesModel).where(SpeciesModel.class_index == class_index))
        stmt = stmt.where(RecognitionRecord.top1_species_id == (sp.id if sp else -1))
    if start_ts is not None:
        stmt = stmt.where(RecognitionRecord.created_at >= start_ts)
    if end_ts is not None:
        stmt = stmt.where(RecognitionRecord.created_at <= end_ts)

    smap = {s.id: s for s in db.scalars(select(SpeciesModel))}
    out = []
    for rec in db.scalars(stmt.order_by(RecognitionRecord.created_at.desc())):
        d = record_to_dict(rec, smap.get(rec.top1_species_id))
        try:
            cands = json.loads(rec.candidates_json)
            d['candidates_text'] = ' | '.join(
                f"{c.get('cn_name')}({c.get('confidence'):.3f})" for c in cands)
        except Exception:
            d['candidates_text'] = ''
        d['model_version'] = rec.model_version
        out.append(d)
    return out


# ---------------- 统计 ----------------

def stats(db: Session) -> dict:
    from app.models import User
    today0 = int(time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)))
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    active_users = db.scalar(select(func.count()).select_from(User)
                             .where(User.status == 1)) or 0
    total_records = db.scalar(select(func.count()).select_from(RecognitionRecord)
                              .where(RecognitionRecord.is_deleted == 0)) or 0
    total_uploads = db.scalar(select(func.count()).select_from(ImageAsset)) or 0
    records_today = db.scalar(select(func.count()).select_from(RecognitionRecord)
                              .where(RecognitionRecord.is_deleted == 0,
                                     RecognitionRecord.created_at >= today0)) or 0
    avg_ms = db.scalar(select(func.avg(RecognitionRecord.duration_ms))) or 0.0

    top_rows = db.execute(
        select(RecognitionRecord.top1_species_id, func.count().label('n'))
        .where(RecognitionRecord.is_deleted == 0)
        .group_by(RecognitionRecord.top1_species_id)
        .order_by(func.count().desc()).limit(5)).all()
    smap = {s.id: s for s in db.scalars(select(SpeciesModel))}
    top_species = [{'cn_name': smap[r[0]].cn_name if r[0] in smap else '?',
                    'class_index': smap[r[0]].class_index if r[0] in smap else -1,
                    'count': r[1]} for r in top_rows]

    return {
        'total_users': total_users,
        'active_users': active_users,
        'total_records': total_records,
        'total_uploads': total_uploads,
        'records_today': records_today,
        'top_species': top_species,
        'avg_duration_ms': round(float(avg_ms), 1),
    }


if __name__ == '__main__':
    print('记录服务自检（内存库）')
    print('-' * 66)
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base
    from app.services.user_service import ensure_admin
    from app.core.security import hash_password

    eng = create_engine('sqlite:///:memory:', future=True)

    @event.listens_for(eng, 'connect')
    def _fk(conn, rec):
        conn.execute('PRAGMA foreign_keys=ON')

    Base.metadata.create_all(eng)
    db = sessionmaker(bind=eng, future=True)()
    ok = fail = 0

    # 准备 species 与一个用户、一张图
    sys.path.insert(0, os.path.join(os.path.dirname(_BACKEND), 'ml'))
    from dataset.species_meta import SPECIES
    now = int(time.time())
    for s in SPECIES:
        db.add(SpeciesModel(id=s.class_index + 1, class_index=s.class_index,
                            cn_name=s.cn_name, latin_name=s.sci_name,
                            common_name=None, morphology='形态描述',
                            habit='习性描述', distribution='分布',
                            image_path=None, created_at=now, updated_at=now))
    db.flush()
    admin = ensure_admin(db)
    db.add(ImageAsset(id=str(uuid.uuid4()), user_id=admin.id,
                      original_filename='t.png', stored_path='20260921/t.png',
                      mime_type='image/png', file_size=100, width=224, height=224,
                      content_hash='a' * 64, created_at=now, expires_at=now + 86400))
    db.flush()
    img = db.scalar(select(ImageAsset))
    smap = load_species_map(db)
    print(f'  species 行数 {len(smap)} （期望 23）')
    ok += (len(smap) == 23); fail += (len(smap) != 23)

    def pred(ci, conf_list):
        cands = []
        for i, (c, cf) in enumerate(zip(ci, conf_list)):
            sp = smap[c]
            cands.append({'rank': i + 1, 'class_index': c, 'cn_name': sp.cn_name,
                          'latin_name': sp.latin_name, 'confidence': cf})
        return {'class_index': ci[0], 'cn_name': smap[ci[0]].cn_name,
                'confidence': conf_list[0], 'candidates': cands,
                'inference_ms': 42, 'model_version': 'v1'}

    # 正常写入
    p = pred([0, 1, 2, 3, 4], [0.9, 0.05, 0.02, 0.02, 0.01])
    rec = save_record(db, user_id=admin.id, image_id=img.id,
                      prediction=p, species_rows=smap)
    db.flush()
    print(f'  ✓ 正常落库 id={rec.id[:8]}… is_low_conf={rec.is_low_confidence}')
    ok += 1

    # 低置信
    p2 = pred([20, 19, 18, 17, 16], [0.4, 0.3, 0.2, 0.05, 0.05])
    rec2 = save_record(db, user_id=admin.id, image_id=img.id,
                       prediction=p2, species_rows=smap)
    db.flush()
    lowok = rec2.is_low_confidence == 1
    ok += lowok; fail += (not lowok)
    print(f'  {"✓" if lowok else "✗"} 低置信标记 is_low_conf={rec2.is_low_confidence}')

    # C-07 校验：篡改 species_id 应被拦
    bad_cands = json.loads(rec.candidates_json)
    bad_cands[0]['species_id'] = 999
    probs = validate_candidates(bad_cands, smap)
    badok = bool(probs)
    ok += badok; fail += (not badok)
    print(f'  {"✓" if badok else "✗"} C-07 捕获 species_id 错位：{probs[:1]}')

    # rank 不连续
    bad2 = json.loads(rec.candidates_json)
    bad2[1]['rank'] = 9
    probs2 = validate_candidates(bad2, smap)
    ok += bool(probs2); fail += (not bool(probs2))
    print(f'  ✓ C-07 捕获 rank 不连续：{probs2[:1]}')

    # 全量扫描
    scan = scan_all_candidates(db)
    scok = scan['bad'] == 0 and scan['total'] == 2
    ok += scok; fail += (not scok)
    print(f'  {"✓" if scok else "✗"} 全量扫描 {scan["total"]} 条，异常 {scan["bad"]} 条')

    # 列表 / 详情 / 删除 / 导出
    items, total = list_records(db, user_id=admin.id)
    print(f'  ✓ 列表 {len(items)} 条 / total={total}')
    ok += 1
    det = record_detail(db, rec)
    print(f'  ✓ 详情 candidates={len(det["candidates"])} species={det["species"]["cn_name"]}')
    ok += 1
    csv_bytes = export_csv(db, collect_for_export(db, user_id=admin.id))
    has_bom = csv_bytes[:3] == b'\xef\xbb\xbf'
    ok += has_bom; fail += (not has_bom)
    print(f'  {"✓" if has_bom else "✗"} CSV 带 UTF-8 BOM（Excel 中文不乱码），{len(csv_bytes)} B')

    n = soft_delete(db, user_id=admin.id, record_ids=[rec2.id], actor=admin)
    left, _ = list_records(db, user_id=admin.id)
    delok = n == 1 and len(left) == 1
    ok += delok; fail += (not delok)
    print(f'  {"✓" if delok else "✗"} 软删除 {n} 条 → 剩余 {len(left)} 条')

    # 越权：他人取记录
    other = None
    got = get_record(db, rec.id, user_id=9999, is_admin=False)
    ok += (got is None); fail += (got is not None)
    print(f'  ✓ 他人取记录被拒（返回 None）')

    st = stats(db)
    print(f'  ✓ 统计 {st}')
    ok += 1

    print()
    print(f'  合计 通过 {ok} / 失败 {fail}')
