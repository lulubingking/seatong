/**
 * 系统接口（管理端配置 / 日志 / 统计 + 公开系统状态）
 * ────────────────────────────────────────────────────────────────
 * 管理端：`/api/admin/config`（2）、`/api/admin/logs`（1）、`/api/admin/stats`（1）
 * 公开：`/api/health`（1）、`/api/model-info`（1）
 *
 * 【命名与方法纪律】配置前缀为 `/api/admin/config`（**带** admin）。
 * 更新走 **`PUT /api/admin/config`**（D8 §9.7），请求体为
 * `{"config": {"<key>": <value>, ...}}` —— **全量覆盖语义、幂等**，
 * 而非 `PATCH /{key}`。语义差异：PUT 提交即生效、重复提交结果一致；
 * 未传的键保持原值（见后端 docstring 说明），因此前端可只提交被改动的项。
 * ────────────────────────────────────────────────────────────────
 */

import { http } from './client'
import { ENDPOINTS } from './index'
import { CONFIG_KEYS } from './types'
import type { AdminStats, ConfigItem, OperationLog, Page } from './types'

/* ── 配置 ────────────────────────────────────────────────────── */

/** GET /api/admin/config —— 返回全部配置项数组（非分页） */
export function getConfig(): Promise<ConfigItem[]> {
  return http.get<ConfigItem[]>(ENDPOINTS.adminConfig)
}

/** PUT /api/admin/config 的响应体 */
export interface ConfigUpdateOut {
  updated: { config_key: string; value: string; value_type: string }[]
}

/**
 * PUT /api/admin/config —— 更新一项或多项配置（整体替换语义）
 *
 * @param patch 形如 `{ guest_quota: 3 }`；值会被服务端按 `value_type` 校验
 */
export function updateConfig(
  patch: Record<string, string | number | boolean>,
): Promise<ConfigUpdateOut> {
  return http.put<ConfigUpdateOut>(ENDPOINTS.adminConfig, { config: patch })
}

/**
 * 把配置数组转为便捷查找表，并按 `value_type` 解析为数字/布尔。
 * 页面读取阈值（如低置信度阈值）时使用。
 */
export interface ParsedConfig {
  guest_quota: number
  batch_upload_limit: number
  max_file_size_mb: number
  image_retention_days: number
  low_confidence_threshold: number
}

export function parseConfig(items: ConfigItem[]): ParsedConfig {
  const get = (key: string, fallback: number): number => {
    const it = items.find((c) => c.config_key === key)
    if (!it) return fallback
    const n = Number(it.value)
    return Number.isFinite(n) ? n : fallback
  }
  return {
    guest_quota: get(CONFIG_KEYS.GUEST_QUOTA, 3),
    batch_upload_limit: get(CONFIG_KEYS.BATCH_UPLOAD_LIMIT, 9),
    max_file_size_mb: get(CONFIG_KEYS.MAX_FILE_SIZE_MB, 10),
    image_retention_days: get(CONFIG_KEYS.IMAGE_RETENTION_DAYS, 180),
    low_confidence_threshold: get(CONFIG_KEYS.LOW_CONFIDENCE_THRESHOLD, 0.6),
  }
}

/* ── 日志与统计 ──────────────────────────────────────────────── */

export interface ListLogsQuery {
  page?: number
  page_size?: number
  user_id?: number
  action?: string
  start_ts?: number
  end_ts?: number
}

/** GET /api/admin/logs */
export function listLogs(q: ListLogsQuery = {}): Promise<Page<OperationLog>> {
  return http.get<Page<OperationLog>>(ENDPOINTS.adminLogs, { params: q })
}

/** GET /api/admin/stats —— 首页与记录管理页的统计卡数据 */
export function getStats(): Promise<AdminStats> {
  return http.get<AdminStats>(ENDPOINTS.adminStats)
}

/* ── 公开系统状态 ────────────────────────────────────────────── */

/** GET /api/health —— 顶栏服务状态指示器 */
export function getHealth(): Promise<{
  status: string
  app: string
  version: string
  /** SQLite 运行参数（foreign_keys 须为 1 / journal_mode 须为 wal） */
  db_pragmas: Record<string, string | number>
  /** ⚠️ 模型状态是**嵌套对象**，不是扁平字段（实测确认） */
  model: {
    ready: boolean
    load_error: string | null
    ckpt: string
    ckpt_exists: boolean
    num_classes: number
    img_size: number
    device: string
    model_version: string | null
    trained_epoch: number | null
    trained_metrics: Record<string, unknown> | null
  }
}> {
  return http.get(ENDPOINTS.health)
}

/** GET /api/model-info —— 关于页展示模型信息 */
export function getModelInfo(): Promise<import('./types').ModelInfo> {
  return http.get<import('./types').ModelInfo>(ENDPOINTS.modelInfo)
}
