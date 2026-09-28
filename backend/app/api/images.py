# -*- coding: utf-8 -*-
"""图像路由 —— D8 §6 images 组（4 个端点）

  POST   /api/images                      上传（不消耗游客额度）
  GET    /api/images/{image_id}/content   取原图
  GET    /api/images/{image_id}/thumb     取缩略图
  DELETE /api/images/{image_id}           删除尚未识别的图片（清理用）

【关键口径】上传【只落盘不推理】，不消耗游客额度；额度在 /api/recognize 扣。
"""

import os
import sys

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.dependencies import (            # noqa: E402
    RATE_LIMIT_DEP, CurrentUser, DbSession, GuestSession, OptionalUser,
    assert_can_access, get_client_ip,
)
from app.core.errors import BizError, E_40001, E_40401, E_42201, ok  # noqa: E402
from app.models import ImageAsset, RecognitionRecord          # noqa: E402
from app.schemas import ImageOut, UploadOut                   # noqa: E402
from app.services import image_service                        # noqa: E402
from app.services.user_service import log_action              # noqa: E402

router = APIRouter(prefix='/images', tags=['images'])


def _find_asset(db, image_id: str) -> ImageAsset:
    ast = db.get(ImageAsset, image_id)
    if ast is None:
        raise BizError(E_40401)
    return ast


@router.post('', dependencies=RATE_LIMIT_DEP)
async def upload_image(db: DbSession, user: OptionalUser, guest: GuestSession,
                       file: UploadFile = File(...)):
    """上传单张图像。

    归属规则：登录用户挂 user_id；游客仅靠 session 标识（user_id 为 NULL），
    后续通过游客的 session 校验归属 —— 但 D7 的 image_asset 未存 session_id，
    故游客上传的图【不设归属】，仅凭 UUID 不可枚举 + 有效期保护。
    """
    raw = await file.read()
    if not raw:
        raise BizError(E_40001, '上传内容为空')

    user_id = user.id if user is not None else None
    asset, reused = image_service.create_asset(
        db, raw, file.filename or 'upload.png', user_id)

    if user is not None:
        log_action(db, action='upload', user=user, target_type='image',
                   target_id=asset.id, detail=f'上传 {asset.original_filename}')
    db.commit()
    return ok({'image': ImageOut.model_validate(asset).model_dump(),
               'reused': reused},
              '图片已缓存' if reused else '上传成功')


@router.get('/{image_id}/content')
def get_image_content(image_id: str, db: DbSession,
                      user: OptionalUser, guest: GuestSession):
    """取原图。归属校验通过后返回二进制。"""
    ast = _find_asset(db, image_id)
    assert_can_access(ast.user_id, user, guest,
                      obj_guest_session=None if ast.user_id else guest)
    # 游客图（user_id 为 NULL）：任何持有 UUID 的人可读 —— UUID 即凭据。
    # 有归属的图：必须本人或管理员。
    raw = image_service.read_bytes(ast)
    return Response(content=raw, media_type=ast.mime_type,
                    headers={'X-Skip-Envelope': '1',
                             'Cache-Control': 'private, max-age=3600'})


@router.get('/{image_id}/thumb')
def get_image_thumb(image_id: str, db: DbSession,
                    user: OptionalUser, guest: GuestSession,
                    size: int = 320):
    ast = _find_asset(db, image_id)
    assert_can_access(ast.user_id, user, guest,
                      obj_guest_session=None if ast.user_id else guest)
    size = max(64, min(1024, size))
    raw = image_service.thumb_bytes(ast, size)
    return Response(content=raw, media_type='image/jpeg',
                    headers={'X-Skip-Envelope': '1',
                             'Cache-Control': 'private, max-age=86400'})


@router.delete('/{image_id}')
def delete_image(image_id: str, db: DbSession, user: CurrentUser,
                 client_ip: str = Depends(get_client_ip)):
    """删除尚未识别的图片（D8 §6.5，清理用）。

    【权限】须登录。游客上传的图归属为空（D7 的 image_asset 未存 session_id），
    无法安全判定"这张图是你的"，故不向游客开放删除 —— 否则任何人凭 UUID
    即可删除他人上传的图。游客图的清理交由过期回收任务处理。

    【归属校验】非本人且非管理员 → 40401（不返回 403，防 ID 枚举）。

    【为什么已识别的图不可删】识别记录（`recognition_record.image_id`）
    对图像资产是 **CASCADE** 外键（D7 §5.2）。若允许删除已有识别记录的图片，
    会连带删除用户的历史记录 —— 那是**数据丢失**而非"清理"。
    故此处显式拦截并返回 42201，提示改用历史记录的删除入口（软删除）。
    """
    ast = _find_asset(db, image_id)

    # 归属校验：本人或管理员
    if not (user.is_admin or ast.user_id == user.id):
        raise BizError(E_40401)

    # 已生成识别记录 → 拒绝（避免级联删掉历史）
    referenced = db.scalar(
        select(RecognitionRecord.id)
        .where(RecognitionRecord.image_id == image_id).limit(1))
    if referenced is not None:
        raise BizError(E_42201,
                       '该图片已产生识别记录，请改用历史记录的删除功能')

    # 先删磁盘文件，再删数据库行 —— 反序会留下无法定位的孤儿文件
    try:
        abs_path = image_service.abs_path_of(ast.stored_path)
        if os.path.exists(abs_path):
            os.remove(abs_path)
    except BizError:
        # 存储路径非法（数据库被篡改）：仍删数据库行，但不碰文件
        pass

    log_action(db, action='delete', user=user, target_type='image',
               target_id=image_id,
               detail=f'删除图片 {ast.original_filename}', ip=client_ip)
    db.delete(ast)
    db.commit()
    return ok(None, '图片已删除')
