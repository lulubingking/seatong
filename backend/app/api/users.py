# -*- coding: utf-8 -*-
"""用户路由 —— D8 §4 / §9 users 组（8 个端点）

**自助（3）**：
  GET    /api/users/me            当前用户信息（含游客额度）
  PATCH  /api/users/me            修改自己的资料
  PUT    /api/users/me/password   修改自己的密码

**管理（5，须 admin 角色）**：
  GET    /api/admin/users                     用户列表（搜索 + 分页）
  POST   /api/admin/users                     创建用户
  PATCH  /api/admin/users/{user_id}           编辑用户（含启用 / 禁用）
  POST   /api/admin/users/{user_id}/reset-password  重置密码
  DELETE /api/admin/users/{user_id}           删除用户

【命名纪律（V1.1 修订，易错）】
· 自助端点走 `/api/users/me*`；管理端点走 **`/api/admin/users*`**。
  D8 §9.1～9.3 明确定义了 admin 前缀，早期实现曾把管理端点并到 `/api/users*`，
  现按文档恢复 —— 避免"用户资源"与"用户管理"两种语义挤在同一命名空间。
· 改密码用 **PUT**（整体替换密码语义，不存在部分更新），不是 POST。
· 重置密码的路径是 `/reset-password`，不是 `/{user_id}/password`。
"""

import os
import sys
import time

from fastapi import APIRouter, Depends, Query

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.dependencies import (            # noqa: E402
    AdminUser, CurrentUser, DbSession, GuestSession, OptionalUser,
    get_client_ip, guest_quota_state,
)
from app.core.errors import BizError, E_40301, ok   # noqa: E402
from app.schemas import (                      # noqa: E402
    AdminResetPasswordIn, AdminUserCreateIn, AdminUserUpdateIn,
    ChangePasswordIn, UserOut,
)
from app.services import user_service           # noqa: E402

router = APIRouter(prefix='/users', tags=['users'])


@router.get('/me')
def get_me(db: DbSession, user: OptionalUser, guest: GuestSession):
    """当前身份。游客返回 is_guest=True 与剩余额度；登录用户返回资料。

    【设计要点】本端点同时服务两种身份，前端首屏只调这一个即可确定状态。
    """
    if user is None:
        return ok({'user': None, 'is_guest': True,
                   'guest_quota': guest_quota_state(db, guest)})
    return ok({'user': UserOut.model_validate(user).model_dump(),
               'is_guest': False, 'guest_quota': None})


@router.patch('/me')
def update_me(db: DbSession, user: CurrentUser, body: AdminUserUpdateIn,
              client_ip: str = Depends(get_client_ip)):
    """修改自己的资料。

    【权限收紧】普通用户不能通过本端点改自己的 role / status ——
    那两个字段由管理员通过管理端点操作，避免提权。
    """
    user_service.admin_update_user(
        db, user, user.id,
        nickname=body.nickname, email=body.email,
        role=None, status=None, ip=client_ip)
    db.commit()
    return ok(UserOut.model_validate(user).model_dump(), '资料已更新')


@router.put('/me/password')
def change_my_password(db: DbSession, user: CurrentUser, body: ChangePasswordIn,
                       client_ip: str = Depends(get_client_ip)):
    """修改自己的密码（D8 §5.7）。

    【为什么是 PUT】本接口是**整体替换密码**语义，不存在部分更新，
    故用 PUT 而非 PATCH（D8 §5.7 业务规则第一条）。
    """
    user_service.change_password(db, user, old=body.old_password,
                                 new=body.new_password, ip=client_ip)
    db.commit()
    return ok(None, '密码已修改，请重新登录')


# ==================== 管理端：/api/admin/users*（D8 §9.1～9.3） ====================

admin_router = APIRouter(prefix='/admin', tags=['admin'])


@admin_router.get('/users')
def list_users(db: DbSession, admin: AdminUser,
               page: int = Query(1, ge=1),
               page_size: int = Query(20, ge=1, le=100),
               keyword: str | None = None,
               role: str | None = Query(None, pattern='^(user|admin)$'),
               status: int | None = Query(None, ge=0, le=1)):
    """用户列表（D8 §9.1）。"""
    rows, total = user_service.list_users(
        db, page=page, page_size=page_size, keyword=keyword,
        role=role, status=status)
    return ok({
        'items': [UserOut.model_validate(r).model_dump() for r in rows],
        'page': page, 'page_size': page_size, 'total': total,
        'total_pages': (total + page_size - 1) // page_size,
    })


@admin_router.post('/users')
def create_user(db: DbSession, admin: AdminUser, body: AdminUserCreateIn,
                client_ip: str = Depends(get_client_ip)):
    """创建用户（管理员）。"""
    u = user_service.register(
        db, username=body.username, password=body.password,
        nickname=body.nickname, email=body.email, ip=client_ip)
    if body.role != 'user':
        u.role = body.role
        db.flush()
    db.commit()
    return ok(UserOut.model_validate(u).model_dump(), '用户已创建')


@admin_router.patch('/users/{user_id}')
def update_user(user_id: int, db: DbSession, admin: AdminUser,
                body: AdminUserUpdateIn,
                client_ip: str = Depends(get_client_ip)):
    """编辑用户 / 启用禁用（D8 §9.2）。"""
    t = user_service.admin_update_user(
        db, admin, user_id, nickname=body.nickname, email=body.email,
        role=body.role, status=body.status, ip=client_ip)
    db.commit()
    return ok(UserOut.model_validate(t).model_dump(), '用户已更新')


@admin_router.post('/users/{user_id}/reset-password')
def reset_user_password(user_id: int, db: DbSession, admin: AdminUser,
                        body: AdminResetPasswordIn,
                        client_ip: str = Depends(get_client_ip)):
    """重置密码（D8 §9.3）。"""
    user_service.admin_reset_password(db, admin, user_id,
                                      body.new_password, ip=client_ip)
    db.commit()
    return ok(None, '密码已重置')


@admin_router.delete('/users/{user_id}')
def delete_user(user_id: int, db: DbSession, admin: AdminUser,
                client_ip: str = Depends(get_client_ip)):
    """删除用户。

    级联行为（D7 §5.2 顺序）：
      1. operation_log.user_id 置 NULL（日志存活）
      2. recognition_record 级联删除
      3. image_asset 置 NULL（等待磁盘清理任务）
      4. 删除 user 行
    SQLAlchemy 的 ORM 关系不处理 image_asset 的 SET NULL，
    故此处显式按顺序操作，与 D7 §5.2 一致。
    """
    from sqlalchemy import select

    from app.models import ImageAsset, RecognitionRecord, User

    target = db.get(User, user_id)
    if target is None:
        raise BizError(40401)
    if target.id == admin.id:
        raise BizError(E_40301, '不能删除自己的账号')
    if target.role == 'admin' and user_service._admin_count(db) <= 1:
        raise BizError(E_40301, '不能删除最后一个管理员')

    uname = target.username

    # 1) 日志置空（保留本体）
    from app.models import OperationLog
    for lg in db.scalars(select(OperationLog).where(
            OperationLog.user_id == target.id)):
        lg.user_id = None

    # 2) 识别记录物理删除（CASCADE 语义，显式执行以便记日志）
    for rec in db.scalars(select(RecognitionRecord).where(
            RecognitionRecord.user_id == target.id)):
        db.delete(rec)

    # 3) 图像资产置空
    for ast in db.scalars(select(ImageAsset).where(
            ImageAsset.user_id == target.id)):
        ast.user_id = None

    db.flush()
    user_service.log_action(db, action='delete', user=admin,
                            target_type='user', target_id=user_id, ip=client_ip,
                            detail=f'删除用户 {uname}')
    db.delete(target)
    db.commit()
    return ok(None, f'用户 {uname} 已删除')
