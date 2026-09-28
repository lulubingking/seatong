# -*- coding: utf-8 -*-
"""历史与结果路由 —— D8 §7 history + §8 result 组

**主路径以文档（PRD §8.1.3 / D8 §7）为权威**：

  GET    /api/records                      历史列表（分页 + 筛选）
  GET    /api/records/{record_id}          记录详情（Top-5 + 物种介绍）
  GET    /api/records/export               导出 CSV
  DELETE /api/records                      批量软删除（集合级）
  DELETE /api/records/{record_id}          单条软删除

**别名（早期联调兼容）**：`/api/history*` 与上表一一对应，共用同一处理函数。
保留别名的理由是前端 V1.0 骨架与部分探针脚本已按 `/api/history` 编写，
切换主路径时可零风险过渡；后续版本可评估移除。

管理端（仅管理员）：
  GET    /api/admin/records                跨用户记录列表
  DELETE /api/admin/records/{record_id}    删除任意用户的单条记录

【易错点·路由顺序】`GET /api/records/export` **必须**声明在
`GET /api/records/{record_id}` 之前。FastAPI 按注册顺序匹配，若 `{record_id}`
在前，`/api/records/export` 会被当作 `record_id="export"` 吞掉，
表现为导出接口永远返回 40401。此处主路径与别名路径各自保持该顺序。
"""

import os
import sys
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.dependencies import (            # noqa: E402
    AdminUser, CurrentUser, DbSession, get_client_ip,
)
from app.core.errors import BizError, E_40401, ok            # noqa: E402
from app.schemas import RecordDeleteIn                        # noqa: E402
from app.services import record_service                       # noqa: E402

router = APIRouter(tags=['history'])
"""主路径路由：`/api/records*`（文档权威）"""

alias_router = APIRouter(tags=['history-alias'])
"""别名路由：`/api/history*`（早期联调兼容，与主路径共用处理函数）"""


def _list_records(db, user, page, page_size, class_index,
                  start_ts, end_ts, keyword):
    items, total = record_service.list_records(
        db, user_id=user.id, page=page, page_size=page_size,
        class_index=class_index, start_ts=start_ts, end_ts=end_ts,
        keyword=keyword)
    return ok({
        'items': items, 'page': page, 'page_size': page_size,
        'total': total, 'total_pages': (total + page_size - 1) // page_size,
    })


def _export_history(db, user, class_index, start_ts, end_ts):
    """导出 CSV。

    【为什么用 X-Skip-Envelope】这是一份文件下载，不套 {code,message,data} 信封，
    否则前端拿到的"CSV"会被包成 JSON，Excel 打不开。
    """
    rows = record_service.collect_for_export(
        db, user_id=user.id, class_index=class_index,
        start_ts=start_ts, end_ts=end_ts)
    data = record_service.export_csv(db, rows)
    fname = f'seatong_history_{time.strftime("%Y%m%d_%H%M%S")}.csv'
    return Response(
        content=data, media_type='text/csv; charset=utf-8',
        headers={
            'X-Skip-Envelope': '1',
            'Content-Disposition':
                f"attachment; filename*=UTF-8''{quote(fname)}",
        })


def _record_detail(record_id, db, user):
    rec = record_service.get_record(db, record_id, user_id=user.id,
                                    is_admin=user.is_admin)
    if rec is None:
        # 不区分"不存在"与"非本人"，统一 40401（防 ID 枚举）
        raise BizError(E_40401)
    return ok(record_service.record_detail(db, rec))


def _delete_records(db, user, body, client_ip):
    n = record_service.soft_delete(db, user_id=user.id,
                                   record_ids=body.record_ids,
                                   is_admin=user.is_admin,
                                   ip=client_ip, actor=user)
    db.commit()
    return ok({'deleted': n}, f'已删除 {n} 条记录')


def _delete_one_record(record_id, db, user, client_ip):
    """单条软删除（对应 D9 §5.6 历史列表的单条删除入口）。

    【为什么与批量端点分开】批量删除用 DELETE + 请求体传 ID 列表；
    单条删除用路径参数更符合 REST 语义，且前端无需构造请求体。
    两者共用 soft_delete 的归属校验逻辑，行为一致。

    【归属校验】非本人且非管理员 → 40401（非 403，防 ID 枚举）。
    soft_delete 内部按 user_id 过滤，取不到即为 0 条 → 需显式区分
    "记录不存在" 与 "已删除"，故先 get_record 判定。
    """
    rec = record_service.get_record(db, record_id, user_id=user.id,
                                    is_admin=user.is_admin)
    if rec is None:
        raise BizError(E_40401)
    n = record_service.soft_delete(db, user_id=user.id,
                                   record_ids=[record_id],
                                   is_admin=user.is_admin,
                                   ip=client_ip, actor=user)
    db.commit()
    return ok({'deleted': n}, '记录已删除')


# ==================== 主路径：/api/records* ====================

@router.get('/records')
def list_records(db: DbSession, user: CurrentUser,
                 page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100),
                 class_index: int | None = Query(None, ge=0, le=22),
                 start_ts: int | None = None,
                 end_ts: int | None = None,
                 keyword: str | None = None):
    """历史列表（D8 §7.1）。"""
    return _list_records(db, user, page, page_size, class_index,
                         start_ts, end_ts, keyword)


@router.get('/records/export')
def export_records(db: DbSession, user: CurrentUser,
                   class_index: int | None = Query(None, ge=0, le=22),
                   start_ts: int | None = None,
                   end_ts: int | None = None):
    """导出 CSV（D8 §7.5）。**须在 `/{record_id}` 之前注册。**"""
    return _export_history(db, user, class_index, start_ts, end_ts)


@router.get('/records/{record_id}')
def get_record_detail(record_id: str, db: DbSession, user: CurrentUser):
    """记录详情（D8 §7.2）。"""
    return _record_detail(record_id, db, user)


@router.delete('/records')
def delete_records(db: DbSession, user: CurrentUser, body: RecordDeleteIn,
                   client_ip: str = Depends(get_client_ip)):
    """批量软删除（D8 §7.4）。"""
    return _delete_records(db, user, body, client_ip)


@router.delete('/records/{record_id}')
def delete_one_record(record_id: str, db: DbSession, user: CurrentUser,
                      client_ip: str = Depends(get_client_ip)):
    """单条软删除（D8 §7.3）。"""
    return _delete_one_record(record_id, db, user, client_ip)


# ==================== 别名路径：/api/history*（兼容） ====================

@alias_router.get('/history')
def list_history(db: DbSession, user: CurrentUser,
                 page: int = Query(1, ge=1),
                 page_size: int = Query(20, ge=1, le=100),
                 class_index: int | None = Query(None, ge=0, le=22),
                 start_ts: int | None = None,
                 end_ts: int | None = None,
                 keyword: str | None = None):
    """别名：同 `GET /api/records`。"""
    return _list_records(db, user, page, page_size, class_index,
                         start_ts, end_ts, keyword)


@alias_router.get('/history/export')
def export_history(db: DbSession, user: CurrentUser,
                   class_index: int | None = Query(None, ge=0, le=22),
                   start_ts: int | None = None,
                   end_ts: int | None = None):
    """别名：同 `GET /api/records/export`。**须在 `/{record_id}` 之前注册。**"""
    return _export_history(db, user, class_index, start_ts, end_ts)


@alias_router.get('/history/{record_id}')
def get_history_detail(record_id: str, db: DbSession, user: CurrentUser):
    """别名：同 `GET /api/records/{record_id}`。"""
    return _record_detail(record_id, db, user)


# ---------------- 管理端：跨用户记录 ----------------

admin_router = APIRouter(prefix='/admin', tags=['admin'])


@admin_router.get('/records')
def admin_list_records(db: DbSession, admin: AdminUser,
                       page: int = Query(1, ge=1),
                       page_size: int = Query(20, ge=1, le=100),
                       class_index: int | None = Query(None, ge=0, le=22),
                       user_id: int | None = None,
                       start_ts: int | None = None,
                       end_ts: int | None = None,
                       keyword: str | None = None):
    """跨用户记录列表（PRD FR-USER-08）。

    与 /api/history 的差异：不限 user_id，并支持按 user_id 过滤。
    """
    items, total = record_service.list_records(
        db, user_id=user_id, page=page, page_size=page_size,
        class_index=class_index, start_ts=start_ts, end_ts=end_ts,
        keyword=keyword, all_users=True)
    return ok({
        'items': items, 'page': page, 'page_size': page_size,
        'total': total, 'total_pages': (total + page_size - 1) // page_size,
    })


@admin_router.delete('/records/{record_id}')
def admin_delete_record(record_id: str, db: DbSession, admin: AdminUser,
                        client_ip: str = Depends(get_client_ip)):
    """删除任意用户的单条记录（PRD FR-USER-08）。"""
    rec = record_service.get_record(db, record_id, user_id=None, is_admin=True)
    if rec is None:
        raise BizError(E_40401)
    n = record_service.soft_delete(db, user_id=admin.id,
                                   record_ids=[record_id],
                                   is_admin=True,
                                   ip=client_ip, actor=admin)
    db.commit()
    return ok({'deleted': n}, '记录已删除')


# ---------------- 结果组：物种 Top-5（结果页补充接口） ----------------

species_router = APIRouter(tags=['result'])


@species_router.get('/results/{record_id}/candidates')
def get_candidates(record_id: str, db: DbSession, user: CurrentUser):
    """单独取某条记录的 Top-5 候选（结果页轮询用）。"""
    rec = record_service.get_record(db, record_id, user_id=user.id,
                                    is_admin=user.is_admin)
    if rec is None:
        raise BizError(E_40401)
    detail = record_service.record_detail(db, rec)
    return ok(detail['candidates'])
