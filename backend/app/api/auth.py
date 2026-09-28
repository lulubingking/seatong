# -*- coding: utf-8 -*-
"""认证路由 —— D8 §3 auth 组（4 个端点）

  POST /api/auth/register   注册
  POST /api/auth/login      登录
  POST /api/auth/refresh    刷新令牌
  POST /api/auth/logout     登出
"""

import os
import sys

from fastapi import APIRouter, Depends

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.dependencies import (            # noqa: E402
    RATE_LIMIT_DEP, CurrentUser, DbSession, GuestSession, get_client_ip,
)
from app.core.errors import ok                  # noqa: E402
from app.schemas import LoginIn, RefreshIn, RegisterIn, UserOut  # noqa: E402
from app.services import user_service           # noqa: E402

router = APIRouter(prefix='/auth', tags=['auth'])


@router.post('/register', dependencies=RATE_LIMIT_DEP)
def register(body: RegisterIn, db: DbSession,
             client_ip: str = Depends(get_client_ip)):
    """注册并直接签发令牌（注册即登录）。"""
    user = user_service.register(
        db, username=body.username, password=body.password,
        nickname=body.nickname, email=body.email, ip=client_ip)
    tokens = user_service.issue_tokens(user)
    db.commit()
    return ok({**tokens,
               'user': UserOut.model_validate(user).model_dump()},
              '注册成功')


@router.post('/login', dependencies=RATE_LIMIT_DEP)
def login(body: LoginIn, db: DbSession,
          client_ip: str = Depends(get_client_ip)):
    user = user_service.authenticate(db, username=body.username,
                                     password=body.password, ip=client_ip)
    tokens = user_service.issue_tokens(user)
    db.commit()
    return ok({**tokens,
               'user': UserOut.model_validate(user).model_dump()},
              '登录成功')


@router.post('/refresh', dependencies=RATE_LIMIT_DEP)
def refresh_token(body: RefreshIn, db: DbSession):
    tokens = user_service.refresh(db, body.refresh_token)
    db.commit()
    return ok(tokens, '令牌已刷新')


@router.post('/logout')
def logout(db: DbSession, user: CurrentUser,
           client_ip: str = Depends(get_client_ip)):
    """登出。

    【说明】JWT 无状态，服务端不维护黑名单，登出仅记录审计日志，
    真正的失效由前端清除本地令牌完成。若不接受这一点，需引入
    令牌黑名单表（D7 未设计），属范围外变更。
    """
    user_service.log_action(db, action='logout', user=user, ip=client_ip,
                            detail='用户登出')
    db.commit()
    return ok(None, '已登出')
