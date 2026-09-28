# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · FastAPI 主应用

启动：
    cd backend
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

端点分组（共 35 个，与 D8 V1.1 逐条对应）：

    auth (4)      /api/auth/*
    users (8)     /api/users/*                  自助 3 + 管理 5
    guest (1)     /api/guest/quota              游客额度（D8 §5.8）
    images (4)    /api/images*                  上传 / 原图 / 缩略图 / 删除
    recognize (2) /api/recognize, /api/recognize/batch
    history (5)   /api/records*                 列表 / 详情 / 删除 ×2 / 导出
    result (1)    /api/results/{id}/candidates
    species (2)   /api/species/*
    admin (8)     /api/admin/*
    system (2)    /api/health, /api/model-info

【命名纪律（V1.1 修订）】
文档侧（PRD §8.1 / D8 §5～9）为唯一权威，实现须与之逐字一致：
    · 历史记录列表/详情/导出走 **`/api/records*`**，不是 `/api/history*`
    · 用户管理走 **`/api/admin/users*`**，不是 `/api/users*`（`/api/users` 仅保留自身资源）
    · 改密码为 **`PUT /api/users/me/password`**（整体替换语义），不是 POST
    · 改配置为 **`PUT /api/admin/config`**（全量覆盖语义），不是 PATCH
    · 物种详情路径参数为 **`{species_id}`**，其值即 `class_index`
为兼容早期联调，`history.py` 仍在 `/api/history*` 保留**同义别名**；
别名与主路径共用同一处理函数，行为完全一致。
"""

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.config import ensure_backend_dirs, settings        # noqa: E402
from app.core.database import Base, engine, pragma_report        # noqa: E402
from app.core.errors import ok                                    # noqa: E402
from app.core.middleware import (                                 # noqa: E402
    EnvelopeMiddleware, RequestContextMiddleware, register_exception_handlers,
)

import app.models  # noqa: F401,E402  触发模型注册


DESCRIPTION = """\
**海瞳鱼鉴 SeaPupil** —— 基于 CNN 的海洋鱼类图像分类系统。

· 23 类海洋鱼类细粒度分类（ResNet18 迁移学习）
· 统一响应体：`{code, message, data, request_id}`，`code=0` 为成功
· 认证：JWT Bearer（access 120 分钟 / refresh 7 天）
· 游客：免登录试用 3 次，凭 `X-Guest-Session` 标识
"""


def create_app() -> FastAPI:
    ensure_backend_dirs()
    Base.metadata.create_all(engine)

    app = FastAPI(
        title='海瞳鱼鉴 SeaPupil API',
        description=DESCRIPTION,
        version=settings.app_version,
        docs_url='/docs',
        redoc_url='/redoc',
        openapi_url='/openapi.json',
    )

    # 中间件注册顺序：后注册的先执行。要让 RequestContext 最外层，最后注册。
    app.add_middleware(EnvelopeMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # 开发环境前端来源：5180 为本项目 dev server（5173 被同机另一项目占用）。
    # 保留 5173/5174 仅为兼容其他联调场景；生产须显式配置实际域名，不得用 `*`。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin,
                       'http://localhost:5180', 'http://127.0.0.1:5180',
                       'http://localhost:5173', 'http://127.0.0.1:5173',
                       'http://localhost:5174', 'http://127.0.0.1:5174'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=['X-Request-Id', 'X-Process-Time-Ms',
                        'Content-Disposition'],
    )

    register_exception_handlers(app)

    # ---- 路由挂载 ----
    from app.api import (auth, guest, history, images, recognize,
                         species_admin, users)

    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(users.router, prefix=settings.api_prefix)
    app.include_router(users.admin_router, prefix=settings.api_prefix)
    app.include_router(guest.router, prefix=settings.api_prefix)
    app.include_router(images.router, prefix=settings.api_prefix)
    app.include_router(recognize.router, prefix=settings.api_prefix)
    app.include_router(history.router, prefix=settings.api_prefix)
    app.include_router(history.alias_router, prefix=settings.api_prefix)
    app.include_router(history.species_router, prefix=settings.api_prefix)
    app.include_router(history.admin_router, prefix=settings.api_prefix)
    app.include_router(species_admin.router, prefix=settings.api_prefix)
    app.include_router(species_admin.admin_router, prefix=settings.api_prefix)

    # ---- 健康检查与元信息 ----
    @app.get('/api/health', tags=['system'])
    def health():
        from app.services.inference import engine as infer_engine
        return ok({
            'status': 'ok',
            'app': settings.app_name,
            'version': settings.app_version,
            'db_pragmas': pragma_report(),
            'model': infer_engine.describe(),
        })

    @app.get('/api/model-info', tags=['system'])
    def model_info():
        """模型元信息。注意：这是 /api/model-info（system 组），
        不是 D8 中并不存在的 /api/recognize/model-info。"""
        from app.services.inference import engine as infer_engine
        d = infer_engine.describe()
        return ok({
            'num_classes': d['num_classes'],
            'img_size': d['img_size'],
            'device': d.get('device'),
            'ready': d['ready'],
            'model_version': d.get('model_version'),
            'trained_epoch': d.get('trained_epoch'),
            'trained_metrics': d.get('trained_metrics'),
        })

    @app.on_event('startup')
    def _warmup():
        """启动时尝试加载模型。失败不阻塞（健康检查会显示 ready=False）。"""
        from app.services.inference import engine as infer_engine
        infer_engine.load(strict=False)
        st = infer_engine.describe()
        print('=' * 72)
        print(f'  {settings.app_name} v{settings.app_version}')
        print(f'  监听       http://{settings.host}:{settings.port}')
        print(f'  文档       http://127.0.0.1:{settings.port}/docs')
        print(f'  模型       {"就绪" if st["ready"] else "未就绪"}'
              f'  device={st.get("device")}  version={st.get("model_version")}')
        if st.get('trained_metrics'):
            m = st['trained_metrics']
            print(f'  指标       acc={m.get("accuracy")} macro_f1={m.get("macro_f1")}')
        if not st['ready'] and st.get('load_error'):
            print(f'  加载错误   {st["load_error"][:200]}')
        print('=' * 72)

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app.main:app', host=settings.host, port=settings.port,
                reload=False)
