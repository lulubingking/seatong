# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 依赖注入层

提供 FastAPI 路由共用的依赖：
  · get_request_id        —— 请求追踪 ID
  · get_client_ip         —— 真实客户端 IP（考虑反代）
  · get_current_user      —— 【必须登录】解析当前用户
  · get_optional_user     —— 【可选登录】游客与登录用户共用端点
  · require_admin         —— 管理员守卫（403）
  · resolve_guest_session —— 游客会话标识（请求头 X-Guest-Session）
  · guest_quota_state     —— 游客额度状态
  · enforce_guest_quota   —— 额度前置检查（42901）
  · consume_guest_quota   —— 额度扣减（仅 /api/recognize 成功后）
  · enforce_rate_limit    —— 限流（42902）

【字段口径对齐 D7】user.status 是 INTEGER 0/1；guest_usage 主键为 session_id；
operation_log 的 IP 列名为 ip。切勿按旧记忆写成文本状态或 guest_token。

PRD 关键口径：
  · 401 系列：40101 未登录/令牌无效 · 40102 已过期 · 40104 已禁用
  · 403 优先于 404 —— 见 assert_can_access 的说明
  · 游客额度在 /api/recognize 成功后扣减，上传不扣
"""

import os
import sys
import time
from typing import Annotated

from fastapi import Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.config import settings                      # noqa: E402
from app.core.database import get_db                      # noqa: E402
from app.core.errors import (                             # noqa: E402
    BizError, E_40101, E_40102, E_40104, E_40301, E_40401, E_42901, E_42902,
)
from app.core.security import (                           # noqa: E402
    TOKEN_ACCESS, TokenError, decode_token, is_locked, lock_remaining_seconds,
)
from app.models import GuestUsage, User                   # noqa: E402

DbSession = Annotated[Session, Depends(get_db)]


# ---------------- 请求上下文 ----------------

def get_request_id(request: Request) -> str:
    """请求追踪 ID。由中间件注入 request.state.request_id。"""
    return getattr(request.state, 'request_id', '') or ''


def get_client_ip(
    request: Request,
    x_forwarded_for: Annotated[str | None, Header(alias='X-Forwarded-For')] = None,
) -> str:
    """真实客户端 IP。反代场景取 X-Forwarded-For 的第一段。"""
    if x_forwarded_for:
        first = x_forwarded_for.split(',')[0].strip()
        if first:
            return first
    return request.client.host if request.client else 'unknown'


# ---------------- 令牌解析 ----------------

def _extract_bearer(authorization: str | None) -> str | None:
    """从 Authorization 头取 Bearer 令牌。"""
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None
    return parts[1].strip() or None


def _load_user_from_token(db: Session, token: str) -> User:
    """解码令牌并取出用户，逐层校验状态。"""
    try:
        payload = decode_token(token, TOKEN_ACCESS)
    except TokenError as e:
        raise BizError(E_40102 if e.expired else E_40101)

    try:
        user_id = int(payload['sub'])
    except (KeyError, TypeError, ValueError):
        raise BizError(E_40101)

    user = db.get(User, user_id)
    if user is None:
        raise BizError(E_40101)
    if not user.is_active:            # status == 1
        raise BizError(E_40104)
    if is_locked(user.locked_until):  # locked_until 是 Unix 时间戳
        mins = lock_remaining_seconds(user.locked_until) // 60 + 1
        raise BizError(E_40102, f'账号已锁定，请 {mins} 分钟后再试')
    return user


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header(alias='Authorization')] = None,
) -> User:
    """【必须登录】。缺失或无效一律抛 40101。"""
    token = _extract_bearer(authorization)
    if not token:
        raise BizError(E_40101)
    return _load_user_from_token(db, token)


def get_optional_user(
    db: DbSession,
    authorization: Annotated[str | None, Header(alias='Authorization')] = None,
    access_token_q: Annotated[str | None, Query(alias='access_token')] = None,
) -> User | None:
    """【可选登录】。

    设计要点：令牌【存在但无效】时抛错，而不是静默降级为游客 ——
    否则用户以为自己登录了，实际额度却按游客算，是更糟的体验。

    【查询参数兜底】`?access_token=` 仅供 `<img>`/`<video>` 等浏览器原生
    请求使用 —— 这类请求无法携带 Authorization 请求头（前端仅对图像
    content/thumb 端点拼接该参数）。常规 JSON 接口一律走请求头，禁止
    把令牌放进 URL（避免落入访问日志）。
    """
    token = _extract_bearer(authorization)
    if not token and access_token_q:
        token = access_token_q.strip() or None
    if not token:
        return None
    return _load_user_from_token(db, token)


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


# ---------------- 角色守卫 ----------------

def require_admin(user: CurrentUser) -> User:
    """管理员守卫。角色不足直接 40301。"""
    if user.role != 'admin':
        raise BizError(E_40301)
    return user


AdminUser = Annotated[User, Depends(require_admin)]


# ---------------- 资源归属校验 ----------------

def assert_can_access(obj_owner_id: int | None,
                      user: User | None,
                      guest_session: str | None,
                      *,
                      obj_guest_session: str | None = None) -> None:
    """资源归属校验（"403 优先于 404" 的正确落地）。

    判定顺序（关键，勿改动）：
      1. 管理员 → 放行
      2. 登录用户：user_id 匹配 → 放行；否则 → 40401
      3. 游客：session_id 匹配 → 放行；否则 → 40401
      4. 无身份 → 40101

    为什么对"他人资源"返回 404 而不是 403？
      PRD 规定"403 优先于 404"的本意是【不要泄露他人资源的存在性】。
      若对他人资源返回 403，攻击者即可通过 403/404 的差异枚举出有效 ID，
      这恰好是 PRD 想避免的。因此"未授权访问他人资源"统一返回 40401。
      40301 保留给"已认证但角色不足"的明确场景（如普通用户调管理端点）。
    """
    if user is not None and user.is_admin:
        return
    if user is not None:
        if obj_owner_id is not None and obj_owner_id == user.id:
            return
        raise BizError(E_40401)
    if guest_session and obj_guest_session and obj_guest_session == guest_session:
        return
    if guest_session:
        raise BizError(E_40401)
    raise BizError(E_40101)


# ---------------- 游客会话与额度 ----------------

def resolve_guest_session(
    x_guest_session: Annotated[str | None, Header(alias='X-Guest-Session')] = None,
    guest_session_q: Annotated[str | None, Query(alias='guest_session')] = None,
) -> str | None:
    """游客会话标识。优先请求头，其次查询参数。"""
    tok = (x_guest_session or guest_session_q or '').strip()
    return tok or None


GuestSession = Annotated[str | None, Depends(resolve_guest_session)]


def get_guest_usage(db: DbSession, guest_session: GuestSession) -> GuestUsage | None:
    """读取游客额度记录。不存在返回 None（尚未使用过）。"""
    if not guest_session:
        return None
    return db.scalar(select(GuestUsage).where(GuestUsage.session_id == guest_session))


def guest_quota_state(db: Session, guest_session: str | None) -> dict:
    """游客额度状态。供 /api/users/me 与 /api/recognize 前置检查共用。"""
    quota = settings.guest_quota
    if not guest_session:
        return {'is_guest': True, 'quota': quota, 'used': 0,
                'remaining': quota, 'known': False}
    usage = db.scalar(select(GuestUsage).where(GuestUsage.session_id == guest_session))
    used = usage.usage_count if usage else 0
    return {
        'is_guest': True,
        'quota': quota,
        'used': used,
        'remaining': max(0, quota - used),
        'known': usage is not None,
    }


def enforce_guest_quota(db: Session, guest_session: str | None) -> None:
    """额度前置检查。用尽抛 42901。"""
    st = guest_quota_state(db, guest_session)
    if st['remaining'] <= 0:
        raise BizError(E_42901,
                       f'游客试用额度已用尽（{st["used"]}/{st["quota"]}），请注册后继续使用')


def consume_guest_quota(db: Session, guest_session: str | None) -> dict:
    """额度扣减。仅由 /api/recognize 成功返回后调用。

    返回扣减后的额度状态，供响应体回给前端。
    """
    if not guest_session:
        return guest_quota_state(db, None)
    now = int(time.time())
    usage = db.scalar(select(GuestUsage).where(GuestUsage.session_id == guest_session))
    if usage is None:
        usage = GuestUsage(session_id=guest_session, usage_count=1,
                           first_seen_at=now, last_seen_at=now)
        db.add(usage)
    else:
        usage.usage_count += 1
        usage.last_seen_at = now
    db.flush()
    return guest_quota_state(db, guest_session)


# ---------------- 限流（进程内滑动窗口，对应 42902） ----------------

_RATE_BUCKETS: dict[str, list[float]] = {}
_RATE_WINDOW = 60.0


def enforce_rate_limit(
    request: Request,
    client_ip: Annotated[str, Depends(get_client_ip)],
) -> None:
    """简易滑动窗口限流。

    单机部署下进程内计数即可满足 PRD。多实例部署需换 Redis。
    """
    key = client_ip
    now = time.time()
    bucket = _RATE_BUCKETS.setdefault(key, [])
    bucket[:] = [t for t in bucket if now - t < _RATE_WINDOW]
    if len(bucket) >= settings.rate_limit_per_minute:
        raise BizError(E_42902,
                       f'请求过于频繁，每分钟上限 {settings.rate_limit_per_minute} 次')
    bucket.append(now)


RateLimited = Annotated[None, Depends(enforce_rate_limit)]

# 【为什么不写 dependencies=[Depends(RateLimited)]】
# RateLimited 已是 Annotated[..., Depends(...)]，再套一层 Depends() 会让
# FastAPI 无法内省，退而把包装层的 *args/**kwargs 当成查询参数，
# 导致每个请求都报 "query.args / query.kwargs: Field required"（40001）。
# 正确写法二选一：
#   ① 路由参数里写 `rl: RateLimited`
#   ② dependencies=[Depends(enforce_rate_limit)] —— 直接放【原始函数】
# 本文件导出 RATE_LIMIT_DEP 供方式 ② 使用，避免各处写错。
RATE_LIMIT_DEP = [Depends(enforce_rate_limit)]


# ---------------- 自检 ----------------

def _selftest() -> int:
    """离线自检：不依赖数据库连接，只验证纯函数逻辑。"""
    from app.core.errors import http_status_of
    print('依赖层自检')
    print('-' * 68)
    fails = 0

    # 1) Bearer 解析
    cases = [
        (None, None), ('', None), ('Token abc', None), ('Bearer', None),
        ('Bearer ', None), ('Bearer abc.def.ghi', 'abc.def.ghi'),
        ('bearer xyz', 'xyz'), ('BEARER q', 'q'),
    ]
    for raw, want in cases:
        got = _extract_bearer(raw)
        ok = got == want
        fails += 0 if ok else 1
        print(f'  {"✓" if ok else "✗"} _extract_bearer({raw!r:24s}) → {got!r}')
    print()

    # 2) 归属校验矩阵
    class _U:
        def __init__(self, uid, role):
            self.id, self.role = uid, role

        @property
        def is_admin(self):
            return self.role == 'admin'

    admin, owner, other = _U(1, 'admin'), _U(2, 'user'), _U(3, 'user')
    matrix = [
        (2, admin, None, None, None),
        (2, owner, None, None, None),
        (2, other, None, None, E_40401),
        (None, other, None, None, E_40401),
        (None, None, 'g1', 'g1', None),
        (None, None, 'g1', 'g2', E_40401),
        (None, None, None, None, E_40101),
        (2, None, None, None, E_40101),
    ]
    for oid, u, gt, ogt, want in matrix:
        try:
            assert_can_access(oid, u, gt, obj_guest_session=ogt)
            got = None
        except BizError as e:
            got = e.code
        ok = got == want
        fails += 0 if ok else 1
        who = f'user#{u.id}/{u.role}' if u else ('guest' if gt else 'anon')
        print(f'  {"✓" if ok else "✗"} owner={str(oid):4s} {who:14s} '
              f'sess={str(gt):4s} obj_sess={str(ogt):4s} → code={got}  (期望 {want})')
    print()

    # 3) 403 语义
    try:
        require_admin(owner)
    except BizError as e:
        ok = e.code == E_40301
        fails += 0 if ok else 1
        print(f'  {"✓" if ok else "✗"} 普通用户调管理端点 → code={e.code} '
              f'HTTP={http_status_of(e.code)} （应为 40301/403）')
    require_admin(admin)
    print('  ✓ 管理员调管理端点   → 放行')
    print()

    print(f'总判定：{"全部通过" if fails == 0 else f"{fails} 项失败"}')
    print()
    print('设计口径提醒：')
    print('  · "他人资源" 一律 40401，而非 40301 —— 403 会泄露 ID 存在性，')
    print('    恰好是 PRD「防 ID 枚举」要避免的。40301 只用于角色不足。')
    print('  · user.status 为 INTEGER 0/1；guest_usage 主键为 session_id。')
    return fails


if __name__ == '__main__':
    sys.exit(1 if _selftest() else 0)
