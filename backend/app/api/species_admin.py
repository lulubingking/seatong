# -*- coding: utf-8 -*-
"""物种与管理路由 —— D8 §8 species + §9 admin 组

物种（公开，无需登录）：
  GET  /api/species                 物种列表（23 类）
  GET  /api/species/{species_id}    单个物种介绍

管理（仅管理员）：
  GET    /api/admin/users           用户管理（见 users.admin_router）
  GET    /api/admin/config          读配置
  PUT    /api/admin/config          更新系统配置（**全量覆盖**语义）
  GET    /api/admin/logs            操作日志
  GET    /api/admin/stats           统计概览

【命名纪律（V1.1 修订，易错）】
· 物种详情的路径参数名是 **`{species_id}`**（D8 §8.2 原文），其取值即 `class_index`。
  实现侧曾写作 `{class_index}`，虽语义相同但与文档不一致，现按文档恢复。
  之所以不改 D7 字段名 `class_index`：该字段是模型 / species / 知识库三处对齐键，
  改名会波及数据库；对外路径参数名则是契约层约定，改它零成本。
· 改配置是 **PUT**（全量覆盖，重复提交结果一致，D8 §1.5 幂等表列明为幂等），
  不是 PATCH。请求体形如 `{"config": {"key": value, ...}}`。
"""

import os
import sys
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.dependencies import (            # noqa: E402
    AdminUser, DbSession, get_client_ip,
)
from app.core.errors import BizError, E_40001, E_40401, ok   # noqa: E402
from app.models import OperationLog, SystemConfig   # noqa: E402
from app.services import record_service             # noqa: E402
from app.services.user_service import log_action    # noqa: E402

router = APIRouter(tags=['species'])


# ==================== 物种（公开） ====================

@router.get('/species')
def list_species(db: DbSession):
    smap = record_service.load_species_map(db)
    items = []
    for ci in sorted(smap):
        s = smap[ci]
        items.append({
            'class_index': s.class_index,
            'cn_name': s.cn_name,
            'latin_name': s.latin_name,
            'common_name': s.common_name,
            'morphology': s.morphology,
            'habit': s.habit,
            'distribution': s.distribution,
            'image_path': s.image_path,
        })
    return ok({'total': len(items), 'items': items})


@router.get('/species/{species_id}')
def get_species(species_id: int, db: DbSession):
    """物种详情（D8 §8.2）。`species_id` 取值即 `class_index`（0～22）。"""
    smap = record_service.load_species_map(db)
    s = smap.get(species_id)
    if s is None:
        raise BizError(E_40401, f'species_id={species_id} 不存在')
    return ok({
        'class_index': s.class_index,
        'cn_name': s.cn_name,
        'latin_name': s.latin_name,
        'common_name': s.common_name,
        'morphology': s.morphology,
        'habit': s.habit,
        'distribution': s.distribution,
        'image_path': s.image_path,
    })


# ==================== 管理 ====================

admin_router = APIRouter(prefix='/admin', tags=['admin'])


@admin_router.get('/config')
def get_config(db: DbSession, admin: AdminUser):
    rows = db.scalars(select(SystemConfig).order_by(SystemConfig.config_key)).all()
    return ok([{
        'config_key': r.config_key,
        'value': r.value,
        'value_type': r.value_type,
        'description': r.description,
        'updated_at': r.updated_at,
    } for r in rows])


@admin_router.put('/config')
def update_config(db: DbSession, admin: AdminUser, body: dict,
                  client_ip: str = Depends(get_client_ip)):
    """更新系统配置（D8 §9.7）。**全量覆盖语义**。

    请求体（D8 §9.7）：
        {"config": {"guest_trial_limit": 3, "max_file_size_mb": 10, ...}}

    仅传入的键会被更新，未出现的键保持原值 —— 所谓"全量"指**提交即生效、
    重复提交结果一致**（幂等），而非"未传即为空"。这样前端可以只改一项。

    【类型校验】按 `value_type` 逐个校验，避免把 "abc" 写进 int 配置。
    任一项不合规则整体回滚（在 commit 之前抛错，无部分写入）。
    """
    payload = body.get('config') if isinstance(body, dict) else None
    if not isinstance(payload, dict) or not payload:
        raise BizError(E_40001, "请求体须形如 {'config': {'<key>': <value>}}")

    updated: list[dict] = []
    for key, raw_val in payload.items():
        row = db.get(SystemConfig, key)
        if row is None:
            raise BizError(E_40401, f'配置项 {key} 不存在')
        raw = str(raw_val)
        # 按 value_type 校验，避免把 "abc" 写进 int 配置
        try:
            if row.value_type == 'int':
                int(raw)
            elif row.value_type == 'float':
                float(raw)
            elif row.value_type == 'bool':
                if raw.lower() not in ('true', 'false', '0', '1'):
                    raise ValueError
        except ValueError:
            raise BizError(
                E_40001, f'配置 {key} 期望 {row.value_type} 类型，收到 {raw!r}')

        old = row.value
        row.value = raw
        row.updated_by = admin.id
        row.updated_at = int(time.time())
        log_action(db, action='config_update', user=admin,
                   target_type='config', target_id=key, ip=client_ip,
                   detail=f'{key}: {old} → {raw}')
        updated.append({'config_key': key, 'value': raw,
                        'value_type': row.value_type})

    db.flush()
    db.commit()
    return ok({'updated': updated}, f'已更新 {len(updated)} 项配置')


@admin_router.get('/logs')
def get_logs(db: DbSession, admin: AdminUser,
             page: int = Query(1, ge=1),
             page_size: int = Query(20, ge=1, le=100),
             action: str | None = None,
             user_id: int | None = None):
    stmt = select(OperationLog)
    cnt = select(func.count()).select_from(OperationLog)
    if action:
        stmt = stmt.where(OperationLog.action == action)
        cnt = cnt.where(OperationLog.action == action)
    if user_id is not None:
        stmt = stmt.where(OperationLog.user_id == user_id)
        cnt = cnt.where(OperationLog.user_id == user_id)

    total = db.scalar(cnt) or 0
    rows = db.scalars(stmt.order_by(OperationLog.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return ok({
        'items': [{
            'id': r.id, 'user_id': r.user_id, 'action': r.action,
            'target_type': r.target_type, 'target_id': r.target_id,
            'ip': r.ip, 'detail': r.detail, 'created_at': r.created_at,
        } for r in rows],
        'page': page, 'page_size': page_size, 'total': total,
        'total_pages': (total + page_size - 1) // page_size,
    })


@admin_router.get('/stats')
def get_stats(db: DbSession, admin: AdminUser):
    return ok(record_service.stats(db))
