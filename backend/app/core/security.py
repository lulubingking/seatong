# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 安全模块（密码哈希 / JWT / 令牌）

对应 PRD 决策基线：
  · JWT + 短期令牌（access 120 分钟）
  · bcrypt 加盐哈希，绝不存明文
  · 登录失败 5 次锁定 15 分钟（对应错误码 40105）

【实现说明 · 2026-09-21】
不使用 passlib —— passlib 1.7.4（2020 年后停更）与 bcrypt 5.x 不兼容：
  · passlib 读取 `bcrypt.__about__.__version__`，bcrypt 4.1+ 已移除该属性 → AttributeError
  · bcrypt 5.x 对超过 72 字节的口令改为【抛异常】而非静默截断
故直接调用 bcrypt 库的原生 API。这也去掉了 passlib 这一层多余的间接性。

bcrypt 的 72 字节上限：bcrypt 算法本身以 72 字节为界，
超长部分不参与哈希。本模块【显式截断】而非任其报错，
并在口令强度校验中限制长度 ≤64【字符】，
但中文等多字节字符编码后可能超过 72 字节，故截断是必要的安全兜底。
"""

import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

# 把 backend/ 加入 sys.path，使 `app.*` 可导入
_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.config import settings  # noqa: E402

# bcrypt 单次哈希的最大字节数（算法硬约束）
BCRYPT_MAX_BYTES = 72

# 令牌类型常量
TOKEN_ACCESS = 'access'
TOKEN_REFRESH = 'refresh'


# ---------------- 密码 ----------------

def _to_bcrypt_bytes(plain: str) -> bytes:
    """编码为 UTF-8 并安全截断到 bcrypt 的 72 字节上限。

    用 `errors='ignore'` 避免截断把多字节字符切成半个导致 UnicodeDecodeError。
    """
    raw = plain.encode('utf-8')
    if len(raw) <= BCRYPT_MAX_BYTES:
        return raw
    # 逐字符累积，保证不在字符中间截断
    out = bytearray()
    for ch in plain:
        b = ch.encode('utf-8')
        if len(out) + len(b) > BCRYPT_MAX_BYTES:
            break
        out.extend(b)
    return bytes(out)


def hash_password(plain: str) -> str:
    """bcrypt 加盐哈希，返回 60 字符的字符串。"""
    return bcrypt.hashpw(_to_bcrypt_bytes(plain),
                         bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode('ascii')


def verify_password(plain: str, hashed: str) -> bool:
    """恒定时间比对。任何异常一律返回 False，不泄露失败原因。"""
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(plain), hashed.encode('ascii'))
    except Exception:
        return False


def password_strength_issues(pw: str) -> list[str]:
    """口令强度校验（注册/改密用）。返回问题清单，空 = 通过。"""
    issues = []
    if len(pw) < 8:
        issues.append('长度至少 8 位')
    if len(pw) > 64:
        issues.append('长度不超过 64 位')
    if not any(c.isalpha() for c in pw):
        issues.append('须包含字母')
    if not any(c.isdigit() for c in pw):
        issues.append('须包含数字')
    return issues


def needs_rehash(hashed: str) -> bool:
    """检查已存哈希的 cost 是否低于当前配置（用于登录时透明升级）。"""
    try:
        rounds = int(hashed.split('$')[2])
        return rounds < settings.bcrypt_rounds
    except Exception:
        return False


# ---------------- JWT ----------------

def _create_token(subject: str | int, token_type: str, expires: timedelta,
                  extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        'sub': str(subject),
        'type': token_type,
        'iat': int(now.timestamp()),
        'exp': int((now + expires).timestamp()),
        'jti': uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: int, role: str) -> str:
    return _create_token(user_id, TOKEN_ACCESS,
                         timedelta(minutes=settings.access_token_expire_minutes),
                         {'role': role})


def create_refresh_token(user_id: int) -> str:
    return _create_token(user_id, TOKEN_REFRESH,
                         timedelta(days=settings.refresh_token_expire_days))


class TokenError(Exception):
    """令牌异常。expired 属性区分'过期'与'无效'，对应 40102 / 40101。"""

    def __init__(self, message: str, expired: bool = False):
        self.expired = expired
        super().__init__(message)


def decode_token(token: str, expect_type: str | None = None) -> dict[str, Any]:
    """解码并校验令牌。失败抛 TokenError（expired 区分两种情形）。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise TokenError('令牌已过期', expired=True)
    except JWTError as e:
        raise TokenError(f'令牌无效: {e.__class__.__name__}', expired=False)

    if expect_type and payload.get('type') != expect_type:
        raise TokenError(f'令牌类型不符，期望 {expect_type}', expired=False)
    if not payload.get('sub'):
        raise TokenError('令牌缺少主体', expired=False)
    return payload


# ---------------- 游客令牌 ----------------

def new_guest_token() -> str:
    """生成游客标识。存于前端 localStorage，用于额度统计。"""
    return uuid.uuid4().hex


# ---------------- 登录失败锁定 ----------------

# 【口径】D7 把 user.locked_until 定义为 INTEGER（Unix 时间戳，UTC），
# 不是 DateTime。以下函数一律按时间戳语义处理，切勿改成 datetime 运算。

def _now_ts() -> int:
    return int(time.time())


def is_locked(locked_until: int | None) -> bool:
    """是否处于锁定中。locked_until 为 None 或已过期 → False。"""
    if locked_until is None:
        return False
    return _now_ts() < int(locked_until)


def lock_remaining_seconds(locked_until: int | None) -> int:
    if locked_until is None:
        return 0
    return max(0, int(locked_until) - _now_ts())


if __name__ == '__main__':
    import bcrypt as _b
    print('安全模块自检')
    print('-' * 62)
    print(f'  bcrypt 版本        {_b.__version__}')
    print(f'  cost rounds        {settings.bcrypt_rounds}')
    print()

    h = hash_password('Test@12345')
    print(f'  哈希前缀           {h[:32]}...')
    print(f'  哈希长度           {len(h)}  （bcrypt 固定 60）')
    print(f'  正确口令验证       {verify_password("Test@12345", h)}')
    print(f'  错误口令验证       {verify_password("wrong", h)}')
    print(f'  空口令验证         {verify_password("", h)}')
    print(f'  畸形哈希不抛异常   {verify_password("x", "not-a-hash")}')
    print()

    # 多字节口令：中文 40 字 = 120 字节，必须被安全截断而非报错
    cn = '密码' * 20
    h2 = hash_password(cn)
    print(f'  中文长口令(120B)   哈希成功 len={len(h2)}')
    print(f'  同一中文口令验证   {verify_password(cn, h2)}')
    print(f'  截断后不同口令区分 {not verify_password("密码" * 20 + "x", h2)}')
    print()

    for pw in ['abc', 'abcdefgh', 'abcdefg1', 'Abcdefg1']:
        iss = password_strength_issues(pw)
        print(f'  口令 {pw!r:12s} → {"通过" if not iss else " / ".join(iss)}')
    print()

    tok = create_access_token(1, 'admin')
    print(f'  access token 长度  {len(tok)}')
    p = decode_token(tok, TOKEN_ACCESS)
    print(f'  解码               sub={p["sub"]} role={p["role"]} type={p["type"]}')
    try:
        decode_token(tok, TOKEN_REFRESH)
    except TokenError as e:
        print(f'  类型不符捕获       TokenError(expired={e.expired})')
    try:
        decode_token(tok + 'x', TOKEN_ACCESS)
    except TokenError as e:
        print(f'  篡改捕获           TokenError(expired={e.expired})')
    print()
    print(f'  游客令牌样例       {new_guest_token()[:24]}...')
    print(f'  cost 过低需重哈希  {needs_rehash("$2b$10$abcdefghijklmnopqrstuv")}  （当前 cost={settings.bcrypt_rounds}）')
    print(f'  cost 达标无需重哈希 {needs_rehash(h)}')
