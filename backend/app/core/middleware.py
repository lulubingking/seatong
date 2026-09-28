# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 中间件

三件事：
  1. 请求 ID 注入（request.state.request_id）+ 回写响应头 X-Request-Id
  2. 统一响应体（把路由返回的 dict 包成 {code, message, data, request_id}）
  3. 全局异常处理（BizError / RequestValidationError / 兜底 Exception）

【为什么用中间件包响应体，而不是每个路由手写】
27 个端点若各自拼 {code,message,data}，极易出现某处漏字段。
统一在中间件收口，路由只返回纯数据，契约由一处保证。
"""

import os
import sys
import time
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.config import settings             # noqa: E402
from app.core.errors import (                    # noqa: E402
    E_40001, E_40401, E_50001, BizError, http_status_of,
)


def _envelope(code: int, message: str, data, request_id: str) -> dict:
    return {'code': code, 'message': message, 'data': data, 'request_id': request_id}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """注入 request_id，并给响应加 X-Request-Id / 耗时头。"""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get('X-Request-Id') or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers['X-Request-Id'] = rid
        response.headers['X-Process-Time-Ms'] = f'{(time.perf_counter() - t0) * 1000:.1f}'
        return response


class EnvelopeMiddleware(BaseHTTPMiddleware):
    """把路由返回的裸 dict/None 包成统一响应体。

    已是信封结构（含 code 键）或非 JSON 响应（文件流）直接放行。
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        ctype = response.headers.get('content-type', '')
        if 'application/json' not in ctype:
            return response
        # 文件下载类端点自行设置 X-Skip-Envelope 跳过包装
        if response.headers.get('X-Skip-Envelope') == '1':
            return response

        # 读出 body
        body = b''
        async for chunk in response.body_iterator:
            body += chunk
        import json as _json
        try:
            payload = _json.loads(body) if body else None
        except Exception:
            return JSONResponse(content=body.decode('utf-8', 'ignore'),
                                status_code=response.status_code,
                                media_type=ctype)

        # 已是信封 → 只补 request_id
        if isinstance(payload, dict) and 'code' in payload and 'message' in payload:
            payload.setdefault('request_id', getattr(request.state, 'request_id', ''))
            out = payload
        else:
            out = _envelope(0, 'ok', payload,
                            getattr(request.state, 'request_id', ''))

        headers = {k: v for k, v in response.headers.items()
                   if k.lower() not in ('content-length', 'content-type')}
        return JSONResponse(content=out, status_code=response.status_code,
                            headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BizError)
    async def _biz(request: Request, exc: BizError):
        return JSONResponse(
            status_code=exc.http_status,
            content=_envelope(exc.code, exc.message, exc.detail,
                              getattr(request.state, 'request_id', '')))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        """Pydantic 校验失败 → 统一映射为 40001，并给出可读的字段级说明。

        【注意】FastAPI 默认返回 422，但 PRD 把"参数校验"归到 400 段，
        故此处显式改写为 400，与错误码 40001 的 HTTP 语义一致。
        """
        detail = []
        for e in exc.errors():
            loc = '.'.join(str(x) for x in e.get('loc', []) if x != 'body')
            detail.append(f'{loc}: {e.get("msg")}')
        return JSONResponse(
            status_code=http_status_of(E_40001),
            content=_envelope(E_40001, '；'.join(detail) or '请求参数错误',
                              exc.errors(), getattr(request.state, 'request_id', '')))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = E_40401 if exc.status_code == 404 else 40001
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail),
                              None, getattr(request.state, 'request_id', '')))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        if settings.debug:
            traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content=_envelope(E_50001, f'服务端内部错误：{type(exc).__name__}',
                              {'detail': str(exc)} if settings.debug else None,
                              getattr(request.state, 'request_id', '')))
