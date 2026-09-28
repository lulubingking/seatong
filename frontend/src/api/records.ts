/**
 * 历史记录接口
 * ────────────────────────────────────────────────────────────────
 * 用户侧：`/api/records*`（5 个端点，D8 §7）
 * 管理端：`/api/admin/records*`（2 个端点，D8 §9.4～9.5）
 *
 * 【命名纪律（易错）】列表 / 详情 / 导出 / 删除**全部**走 `/api/records*`。
 * 早期实现曾把列表与详情放在 `/api/history*`，现已按 D8 统一到 records；
 * 后端保留了 `/api/history*` 同义别名，但**前端不再使用**，新代码一律用 records。
 * 批量删除是 `DELETE /api/records`（集合级），**不是** `/api/records/batch`。
 * ────────────────────────────────────────────────────────────────
 */

import { http } from './client'
import { ENDPOINTS } from './index'
import type {
  DeleteOut,
  HistoryListQuery,
  Page,
  RecordDeleteIn,
  RecordDetailOut,
  RecordItem,
} from './types'

/* ── 用户侧 ──────────────────────────────────────────────────── */

/**
 * GET /api/records
 * 返回分页记录列表。服务端仅返回 `user_id = 当前用户` 的记录；
 * 访问他人记录一律 40401（防 ID 枚举）。
 */
export function listHistory(q: HistoryListQuery = {}): Promise<Page<RecordItem>> {
  return http.get<Page<RecordItem>>(ENDPOINTS.records, { params: q })
}

/** GET /api/records/{record_id} —— 详情（含候选、物种、原图） */
export function getHistoryDetail(recordId: string): Promise<RecordDetailOut> {
  return http.get<RecordDetailOut>(ENDPOINTS.recordById(recordId))
}

/**
 * DELETE /api/records —— 批量软删除
 * 传 1 个 ID 亦可当作单条删除，但单条请优先用 {@link deleteOneRecord}（语义更清晰）。
 */
export function deleteRecords(ids: string[]): Promise<DeleteOut> {
  const body: RecordDeleteIn = { record_ids: ids }
  return http.delete<DeleteOut>(ENDPOINTS.records, { data: body })
}

/** DELETE /api/records/{record_id} —— 单条软删除（D9 §5.6 列表行内删除入口） */
export function deleteOneRecord(recordId: string): Promise<DeleteOut> {
  return http.delete<DeleteOut>(ENDPOINTS.recordById(recordId))
}

/**
 * GET /api/records/export —— 导出 CSV（带 UTF-8 BOM）
 *
 * 该端点**不返回 JSON 信封**，而是 `Content-Disposition: attachment` 的二进制流，
 * 故绕过 `http` 辅助函数，直接取 blob。
 */
export async function exportHistoryCsv(q: HistoryListQuery = {}): Promise<Blob> {
  const resp = await http.raw.get(ENDPOINTS.recordsExport,
    { params: q, responseType: 'blob' })
  return resp.data as Blob
}

/** 触发浏览器下载（导出 CSV 用） */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/* ── 管理端 ──────────────────────────────────────────────────── */

/**
 * GET /api/admin/records —— 跨用户记录列表（PRD FR-USER-08）
 * `user_id` 为可选过滤器：不传 = 全部用户。
 */
export function adminListRecords(
  q: HistoryListQuery & { user_id?: number } = {},
): Promise<Page<RecordItem>> {
  return http.get<Page<RecordItem>>(ENDPOINTS.adminRecords, { params: q })
}

/** DELETE /api/admin/records/{record_id} —— 删除任意用户的单条记录 */
export function adminDeleteRecord(recordId: string): Promise<DeleteOut> {
  return http.delete<DeleteOut>(ENDPOINTS.adminRecordById(recordId))
}
