# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 用户服务

职责：
  · 注册（用户名不区分大小写查重 → 40901）
  · 登录（失败计数 + 锁定 → 40103 / 40104 / 40105）
  · 令牌签发与刷新
  · 改密、管理端用户 CRUD
  · 操作日志写入（对应 operation_log.action 的 9 种取值）

【DB-R03 关键差异】operation_log.user_id 为 SET NULL（审计日志须存活），
recognition_record.user_id 为 CASCADE（记录随账号清理）。
"""

import os
import sys
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.config import settings                      # noqa: E402
from app.core.errors import (                             # noqa: E402
    BizError, E_40001, E_40101, E_40103, E_40104, E_40105,
    E_40301, E_40401, E_40901,
)
from app.core.security import (                           # noqa: E402
    TOKEN_ACCESS, TOKEN_REFRESH, TokenError, create_access_token,
    create_refresh_token, decode_token, hash_password, is_locked,
    lock_remaining_seconds, needs_rehash, password_strength_issues,
    verify_password,
)
from app.models import LOG_ACTIONS, OperationLog, User     # noqa: E402


# ---------------- 操作日志 ----------------

def log_action(db: Session, *, action: str, user: User | None = None,
               target_type: str | None = None, target_id: str | None = None,
               ip: str | None = None, detail: str = '') -> OperationLog:
    """写一条操作日志。

    【为什么多存一个 user_id 之外的快照】user_id 为 SET NULL，
    账号删除后日志会失去归属者；故同时写入昵称/用户名快照。
    注意 operation_log 表本身没有 username_snapshot 列（D7 未设计），
    故快照写入 detail 前缀，避免越权改表结构。
    """
    if action not in LOG_ACTIONS:
        raise ValueError(f'未知的 action: {action}（合法值 {LOG_ACTIONS}）')
    who = ''
    if user is not None:
        who = f'[{user.username}] '
    entry = OperationLog(
        user_id=user.id if user else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        ip=ip,
        detail=(who + detail)[:500],
        created_at=int(time.time()),
    )
    db.add(entry)
    return entry


# ---------------- 注册 ----------------

def find_by_username(db: Session, username: str) -> User | None:
    """按用户名查找，【不区分大小写】（BR-USER-01）。

    数据库层已有 idx_user_username_lower 函数唯一索引兜底；
    这里用 func.lower() 查询以命中该索引。
    """
    return db.scalar(select(User).where(func.lower(User.username) == username.lower()))


def register(db: Session, *, username: str, password: str,
             nickname: str = '', email: str | None = None,
             ip: str | None = None) -> User:
    issues = password_strength_issues(password)
    if issues:
        raise BizError(E_40001, '；'.join(issues))
    if find_by_username(db, username) is not None:
        raise BizError(E_40901, f'用户名 {username} 已存在')

    now = int(time.time())
    user = User(
        username=username,
        password_hash=hash_password(password),
        nickname=nickname or username,
        email=email,
        role='user',
        status=1,
        failed_login_count=0,
        locked_until=None,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    log_action(db, action='login', user=user, ip=ip, detail='注册即登录')
    return user


# ---------------- 登录 ----------------

def authenticate(db: Session, *, username: str, password: str,
                 ip: str | None = None) -> User:
    """校验凭据。失败分类对应 40103 / 40104 / 40105。

    【安全要点】用户名不存在与密码错误【返回同一错误码 40103】，
    不区分"用户不存在"与"密码错误"，避免用户名枚举。
    """
    user = find_by_username(db, username)

    if user is None:
        raise BizError(E_40103)       # 与密码错误同码，防枚举

    # 锁定优先于密码校验
    if is_locked(user.locked_until):
        mins = lock_remaining_seconds(user.locked_until) // 60 + 1
        raise BizError(E_40105, f'账号已锁定，请 {mins} 分钟后再试')

    if not verify_password(password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.login_max_failures:
            user.locked_until = int(time.time()) + settings.login_lock_minutes * 60
            user.failed_login_count = 0      # 锁定后清零，解锁即重新计数
            db.flush()
            raise BizError(E_40105,
                           f'连续失败 {settings.login_max_failures} 次，'
                           f'账号锁定 {settings.login_lock_minutes} 分钟')
        db.flush()
        left = settings.login_max_failures - user.failed_login_count
        raise BizError(E_40103, f'用户名或密码不正确（还可尝试 {left} 次）')

    if user.status != 1:
        raise BizError(E_40104, '账号已被禁用，请联系管理员')

    # 登录成功：清零失败计数，必要时透明升级哈希 cost
    user.failed_login_count = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    db.flush()
    log_action(db, action='login', user=user, ip=ip, detail='登录成功')
    return user


def issue_tokens(user: User) -> dict:
    return {
        'access_token': create_access_token(user.id, user.role),
        'refresh_token': create_refresh_token(user.id),
        'token_type': 'bearer',
        'expires_in': settings.access_token_expire_minutes * 60,
    }


def refresh(db: Session, refresh_token: str) -> dict:
    """用 refresh 令牌换新令牌对。"""
    try:
        payload = decode_token(refresh_token, TOKEN_REFRESH)
    except TokenError as e:
        raise BizError(E_40101 if not e.expired else E_40101, '刷新令牌无效或已过期')
    user = db.get(User, int(payload['sub']))
    if user is None or user.status != 1:
        raise BizError(E_40104 if user is not None else E_40101)
    if is_locked(user.locked_until):
        raise BizError(E_40105, '账号已锁定')
    return issue_tokens(user)


# ---------------- 改密 ----------------

def change_password(db: Session, user: User, *, old: str,
                    new: str, ip: str | None = None) -> None:
    if not verify_password(old, user.password_hash):
        raise BizError(E_40103, '原密码不正确')
    issues = password_strength_issues(new)
    if issues:
        raise BizError(E_40001, '；'.join(issues))
    if verify_password(new, user.password_hash):
        raise BizError(E_40001, '新密码不能与原密码相同')
    user.password_hash = hash_password(new)
    user.updated_at = int(time.time())
    db.flush()
    log_action(db, action='password_reset', user=user, ip=ip, detail='用户自助改密')


# ---------------- 管理端 ----------------

def admin_create_user(db: Session, actor: User, **kw) -> User:
    """管理员建号。不改动 actor 的日志语义，仅记录被创建者。"""
    return register(db, **kw)


def admin_update_user(db: Session, actor: User, target_id: int,
                      *, nickname=None, email=None, role=None, status=None,
                      ip: str | None = None) -> User:
    target = db.get(User, target_id)
    if target is None:
        raise BizError(E_40401)

    # 保护规则（D8 补充码语义，此处以 40301 承载）
    if role is not None and role != target.role:
        if target.id == actor.id:
            raise BizError(E_40301, '不能修改自己的角色')
        if target.role == 'admin' and role == 'user' and _admin_count(db) <= 1:
            raise BizError(E_40301, '不能降级最后一个管理员')

    if status is not None and status != target.status:
        if target.id == actor.id:
            raise BizError(E_40301, '不能禁用自己的账号')
        if status == 0 and target.role == 'admin' and _admin_count(db) <= 1:
            raise BizError(E_40301, '不能禁用最后一个管理员')

    if nickname is not None:
        target.nickname = nickname
    if email is not None:
        target.email = email
    if role is not None:
        target.role = role
    if status is not None:
        target.status = status
    target.updated_at = int(time.time())
    db.flush()

    if status == 0:
        log_action(db, action='user_disable', user=actor,
                   target_type='user', target_id=target.id, ip=ip,
                   detail=f'禁用用户 {target.username}')
    else:
        log_action(db, action='config_update', user=actor,
                   target_type='user', target_id=target.id, ip=ip,
                   detail=f'修改用户 {target.username}')
    return target


def admin_reset_password(db: Session, actor: User, target_id: int,
                         new_password: str, ip: str | None = None) -> None:
    target = db.get(User, target_id)
    if target is None:
        raise BizError(E_40401)
    if target.id == actor.id:
        raise BizError(E_40301, '请使用「修改密码」修改自己的密码')
    if target.role == 'admin' and actor.id != target.id:
        # 允许管理员重置他人，但禁止重置其他管理员（避免互相夺权）
        if _admin_count(db) > 1:
            raise BizError(E_40301, '不能重置其他管理员的密码')
    issues = password_strength_issues(new_password)
    if issues:
        raise BizError(E_40001, '；'.join(issues))
    target.password_hash = hash_password(new_password)
    target.failed_login_count = 0
    target.locked_until = None
    target.updated_at = int(time.time())
    db.flush()
    log_action(db, action='password_reset', user=actor,
               target_type='user', target_id=target.id, ip=ip,
               detail=f'重置 {target.username} 的密码')


def _admin_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(
        User.role == 'admin', User.status == 1)) or 0


def list_users(db: Session, *, page: int = 1, page_size: int = 20,
               keyword: str | None = None, role: str | None = None,
               status: int | None = None) -> tuple[list[User], int]:
    stmt = select(User)
    cnt = select(func.count()).select_from(User)
    if keyword:
        like = f'%{keyword}%'
        stmt = stmt.where(User.username.like(like) | User.nickname.like(like))
        cnt = cnt.where(User.username.like(like) | User.nickname.like(like))
    if role:
        stmt = stmt.where(User.role == role)
        cnt = cnt.where(User.role == role)
    if status is not None:
        stmt = stmt.where(User.status == status)
        cnt = cnt.where(User.status == status)
    total = db.scalar(cnt) or 0
    rows = db.scalars(stmt.order_by(User.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return list(rows), total


def ensure_admin(db: Session, *, username: str = 'admin',
                 password: str = 'Admin@12345') -> User:
    """确保存在一个管理员账号（首次初始化用）。幂等。"""
    u = find_by_username(db, username)
    if u is not None:
        if u.role != 'admin':
            u.role = 'admin'
            u.status = 1
            db.flush()
        return u
    now = int(time.time())
    u = User(username=username, password_hash=hash_password(password),
             nickname='系统管理员', email=None, role='admin', status=1,
             failed_login_count=0, locked_until=None,
             created_at=now, updated_at=now)
    db.add(u)
    db.flush()
    return u


if __name__ == '__main__':
    print('用户服务自检（内存库，不触碰真实 seatong.db）')
    print('-' * 66)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base

    eng = create_engine('sqlite:///:memory:', future=True)
    from sqlalchemy import event

    @event.listens_for(eng, 'connect')
    def _fk(conn, rec):
        conn.execute('PRAGMA foreign_keys=ON')

    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, future=True)
    db = S()

    ok = fail = 0

    def case(name, fn, expect_code=None):
        global ok, fail
        try:
            r = fn()
            got = None
        except BizError as e:
            r, got = None, e.code
        good = got == expect_code
        ok += good; fail += (not good)
        print(f'  {"✓" if good else "✗"} {name:<40s} → {got} (期望 {expect_code})')
        return r

    admin = ensure_admin(db)
    print(f'  管理员: id={admin.id} role={admin.role}')
    db.flush()

    u = case('注册 alice', lambda: register(db, username='alice', password='Passw0rd1',
                                           nickname='爱丽丝'), None)
    db.flush()
    case('注册 ALICE（大小写查重）',
         lambda: register(db, username='ALICE', password='Passw0rd1'), 40901)
    case('注册弱口令 abc',
         lambda: register(db, username='bob', password='abc'), 40001)
    case('注册无数字口令',
         lambda: register(db, username='bob2', password='abcdefgh'), 40001)
    print()

    case('登录 alice 正确', lambda: authenticate(db, username='alice', password='Passw0rd1'), None)
    case('登录 ALICE（大小写不敏感）',
         lambda: authenticate(db, username='ALICE', password='Passw0rd1'), None)
    case('登录 密码错误', lambda: authenticate(db, username='alice', password='wrong'), 40103)
    case('登录 用户不存在（同码防枚举）',
         lambda: authenticate(db, username='nobody', password='x'), 40103)
    print()

    # 连续失败触发锁定
    b = case('注册 bob3', lambda: register(db, username='bob3', password='Passw0rd1'), None)
    db.flush()
    for i in range(4):
        try:
            authenticate(db, username='bob3', password='bad')
        except BizError as e:
            print(f'      第 {i + 1} 次失败 → {e.code}')
    case('第 5 次失败触发锁定', lambda: authenticate(db, username='bob3', password='bad'), 40105)
    case('锁定期内正确密码也拒绝',
         lambda: authenticate(db, username='bob3', password='Passw0rd1'), 40105)
    print()

    # 令牌
    tk = issue_tokens(u)
    print(f'  令牌签发: access {len(tk["access_token"])} 字符, '
          f'expires_in={tk["expires_in"]}s')
    d = decode_token(tk['access_token'], TOKEN_ACCESS)
    print(f'  解码: sub={d["sub"]} role={d["role"]}')
    case('刷新令牌', lambda: refresh(db, tk['refresh_token']), None)
    case('用 access 冒充 refresh', lambda: refresh(db, tk['access_token']), 40101)
    print()

    # 改密
    case('改密 原密码错', lambda: change_password(db, u, old='bad', new='NewPass99'), 40103)
    case('改密 新密码弱', lambda: change_password(db, u, old='Passw0rd1', new='abc'), 40001)
    case('改密 新旧相同', lambda: change_password(db, u, old='Passw0rd1', new='Passw0rd1'), 40001)
    case('改密 正常', lambda: change_password(db, u, old='Passw0rd1', new='NewPass99'), None)
    case('改密后用新密码登录',
         lambda: authenticate(db, username='alice', password='NewPass99'), None)
    print()

    # 管理端保护
    case('禁用自己', lambda: admin_update_user(db, admin, admin.id, status=0), 40301)
    case('修改自己角色', lambda: admin_update_user(db, admin, admin.id, role='user'), 40301)
    case('降级最后一个管理员',
         lambda: admin_update_user(db, admin, admin.id, role='user'), 40301)
    case('禁用普通用户', lambda: admin_update_user(db, admin, u.id, status=0), None)
    case('被禁用后登录', lambda: authenticate(db, username='alice', password='NewPass99'), 40104)
    case('重置自己密码（应引导用改密）',
         lambda: admin_reset_password(db, admin, admin.id, 'Admin@9999'), 40301)
    print()

    # 日志
    from app.models import OperationLog as OL
    n = db.scalar(select(func.count()).select_from(OL))
    print(f'  操作日志条数: {n}')
    for r in db.scalars(select(OL).limit(3)):
        print(f'    [{r.action:14s}] {r.detail}')
    print()
    print(f'  合计 通过 {ok} / 失败 {fail}')
