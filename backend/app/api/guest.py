# -*- coding: utf-8 -*-
"""游客路由 —— D8 §5.8 游客额度查询

  GET /api/guest/quota    查询游客剩余试用次数

【与 /api/users/me 的分工】
`/api/users/me` 同时返回身份与额度（内嵌 `guest_quota` 字段），供首屏一次调用
确定状态；本端点则是**纯额度查询**，供识别前的额度刷新或额度用尽提示使用。
两者共用 `guest_quota_state()` 这一唯一数据源，因此结果必然一致。

【字段口径（易错）】
D8 §5.8 定义响应字段为 `limit` / `used` / `remaining`，
而 `guest_quota_state()` 内部键名为 `quota` / `used` / `remaining`。
本端点在此做一次**显式改名**：`quota` → `limit`，并剥掉内部字段
（`is_guest` / `known`），使对外契约与 D8 逐字一致。
"""

import os
import sys

from fastapi import APIRouter

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.dependencies import (            # noqa: E402
    DbSession, GuestSession, OptionalUser, guest_quota_state,
)
from app.core.errors import ok                 # noqa: E402

router = APIRouter(prefix='/guest', tags=['guest'])


@router.get('/quota')
def get_guest_quota(db: DbSession, user: OptionalUser, guest: GuestSession):
    """查询游客剩余试用次数（D8 §5.8 / PRD FR-USER-06）。

    【已登录用户的行为】返回三者均为 0（D8 §5.8 明文规定）。
    理由是登录用户不受游客额度限制，返回非零值会让前端误显示额度药丸。

    【remaining 的下限截断】`guest_quota_state()` 内部已用 `max(0, ...)` 处理，
    故管理员下调上限后不会出现负数（D8 §5.8 业务规则第三条）。

    【额度在服务端计数】读 `guest_usage` 表而非前端本地存储，
    清理浏览器缓存无法绕过限制（PRD BR-USER-12）。
    """
    if user is not None:
        return ok({'limit': 0, 'used': 0, 'remaining': 0})

    st = guest_quota_state(db, guest)
    return ok({
        'limit': st['quota'],          # 内部键名 quota → 对外 limit
        'used': st['used'],
        'remaining': st['remaining'],
    })
