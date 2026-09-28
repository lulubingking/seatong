/**
 * API 类型定义
 * ────────────────────────────────────────────────────────────────
 * 字段命名纪律（D9 §10.4.5）：
 *   · 前端类型**保持 API 原样**（snake_case），不做 camelCase 转换
 *   · 类型定义须与后端响应**逐字符一致**
 *
 * 【重要】本文件的字段名不来自 PRD §8.1 / D8 的旧版契约，而是以
 * **后端真实响应实测**为准（2026-09-21 逐端点探测）。四处已知偏离：
 *   1. 结果外层键为 `class_index` + `cn_name` + `latin_name`（非 `top1` 嵌套对象）
 *   2. 时间字段为 INTEGER Unix 时间戳（秒），**非** ISO 字符串
 *   3. `upload` 返回 `{image, reused}`（非扁平 image 对象）
 *   4. `me` 返回 `{user, is_guest, guest_quota}`（游客额度内联，无独立端点）
 * ────────────────────────────────────────────────────────────────
 */

/* ══════════════════════════════════════════════════════════════
   统一响应信封
   —— 恒为 `{code, message, data, request_id}`，`code === 0` 表示成功
   —— 业务失败也返回 HTTP 200（除鉴权失败外），须按 `code` 分派
   ══════════════════════════════════════════════════════════════ */

export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
  request_id: string
}

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

/** 归一化后的业务错误（由响应拦截器抛出，页面按 level 分派呈现） */
export interface ApiError extends Error {
  code: string
  httpStatus: number | null
  level: 'field' | 'block' | 'global'
  retryable: boolean
  requestId: string | null
}

/* ══════════════════════════════════════════════════════════════
   用户与会话
   ══════════════════════════════════════════════════════════════ */

import type { UserRole, UserStatus } from '@/constants/enums'

export interface User {
  id: number
  username: string
  nickname: string | null
  email: string | null
  role: UserRole
  /** INTEGER 0/1（D7），非布尔 */
  status: UserStatus
  /** Unix 时间戳（秒） */
  created_at: number
}

export interface LoginIn {
  username: string
  password: string
}

export interface LoginOut {
  access_token: string
  refresh_token: string
  token_type: string
  /** 秒。access 120 min = 7200 */
  expires_in: number
  user: User
}

export interface RegisterIn {
  username: string
  password: string
  nickname?: string
  email?: string | null
}

export interface RefreshIn {
  refresh_token: string
}

export interface ChangePasswordIn {
  old_password: string
  new_password: string
}

export interface UpdateMeIn {
  nickname?: string | null
  email?: string | null
}

/**
 * 游客额度状态。
 *
 * 【两个端点的字段名有意不同（易错）】
 * · `GET /api/users/me` → `guest_quota` 内嵌对象：字段名是 **`quota`**，
 *   并带内部标记 `is_guest` / `known`。用于首屏一次拿全"身份 + 额度"。
 * · `GET /api/guest/quota` → 独立端点：字段名是 **`limit`**（D8 §5.8），
 *   且**不含** `is_guest` / `known`（对外契约收敛）。见 {@link GuestQuotaOut}。
 *
 * 之所以不强行统一：前者是"身份响应的一部分"，后者是"纯额度响应"，
 * 两者的对外契约在 D8 中分别定义（§5.5 与 §5.8）。前端按端点选型即可。
 *
 * `known=false` 表示尚未在服务端登记过 {@link HEADER_GUEST_SESSION}。
 */
export interface GuestQuota {
  is_guest: boolean
  /** 试用次数上限。注意本字段名为 `quota`，独立端点为 `limit` */
  quota: number
  used: number
  remaining: number
  known: boolean
}

/** `GET /api/guest/quota` 的返回（D8 §5.8）。字段名是 `limit`，且无内部标记 */
export interface GuestQuotaOut {
  limit: number
  used: number
  remaining: number
}

/** `GET /api/users/me` 的返回。游客访问时 `user` 为 null */
export interface MeOut {
  user: User | null
  is_guest: boolean
  guest_quota: GuestQuota
}

/* ── 管理端用户 ─────────────────────────────────────────────── */

export interface AdminUserCreateIn {
  username: string
  password: string
  nickname?: string
  email?: string | null
  role?: UserRole
}

export interface AdminUserUpdateIn {
  nickname?: string | null
  email?: string | null
  role?: UserRole | null
  /** INTEGER 0/1 */
  status?: UserStatus | null
}

export interface AdminResetPasswordIn {
  new_password: string
}

/* ══════════════════════════════════════════════════════════════
   图片资源
   ══════════════════════════════════════════════════════════════ */

export interface ImageAsset {
  /** UUID 字符串（TEXT(36)） */
  id: string
  original_filename: string
  mime_type: string
  file_size: number
  width: number
  height: number
  content_hash: string
  created_at: number
  /** 保留期到期时间戳（默认 +180 天） */
  expires_at: number
}

export interface UploadOut {
  image: ImageAsset
  /** true = 内容哈希命中已有资源，未重复落盘 */
  reused: boolean
}

/* ══════════════════════════════════════════════════════════════
   物种
   ══════════════════════════════════════════════════════════════ */

export interface Species {
  /** 0–22，全系统唯一对齐键（D9 §9.2.1） */
  class_index: number
  cn_name: string
  latin_name: string
  /** 目录名，如 `fish_1` */
  common_name: string
  morphology: string
  habit: string
  distribution: string
  image_path: string | null
}

export interface SpeciesListOut {
  total: number
  items: Species[]
}

/* ══════════════════════════════════════════════════════════════
   识别
   ══════════════════════════════════════════════════════════════ */

export interface RecognizeIn {
  image_id: string
  /** 1–23，默认 5 */
  top_k?: number
}

export interface Candidate {
  /** 1 起 */
  rank: number
  class_index: number
  cn_name: string
  latin_name: string
  /** 0–1 浮点，展示时保留 1 位小数（D9 §3.6 D-02） */
  confidence: number
}

/** 单张识别的完整结果 */
export interface RecognizeOut {
  /** 游客识别不落库，此字段为 null（D7 §2.2） */
  record_id: string | null
  image: ImageAsset
  class_index: number
  cn_name: string
  latin_name: string
  confidence: number
  /** 后端依据 `low_confidence_threshold` 配置判定 */
  is_low_confidence: boolean
  /** 长度 = top_k */
  candidates: Candidate[]
  species: Species
  /** 整数毫秒（D9 §3.6 D-04） */
  duration_ms: number
  model_version: string
  /** 游客时为额度状态；登录用户为 null */
  guest_quota: GuestQuota | null
}

export interface BatchRecognizeIn {
  /** 1–9 张（与 `batch_upload_limit` 一致） */
  image_ids: string[]
  top_k?: number
}

/** 批量识别的单张结果条目。失败时 `data` 为 null，`code` 为业务错误码 */
export interface BatchItemResult {
  image_id: string
  code: number
  message: string
  data: RecognizeOut | null
}

export interface BatchRecognizeOut {
  total: number
  /** 实际处理的张数。额度中途耗尽时 < total */
  processed: number
  succeeded: number
  failed: number
  results: BatchItemResult[]
  guest_quota: GuestQuota | null
}

/* ══════════════════════════════════════════════════════════════
   历史记录
   ══════════════════════════════════════════════════════════════ */

import type { RecordStatus } from '@/constants/enums'

/** 列表项（历史列表 / 管理端记录列表共用） */
export interface RecordItem {
  id: string
  class_index: number
  cn_name: string
  latin_name: string
  confidence: number
  is_low_confidence: boolean
  duration_ms: number
  status: RecordStatus
  created_at: number
  /** 游客记录为 null；但游客记录本身不落库，此处通常非 null */
  image_id: string | null
  /** 相对路径，需拼 baseURL。原图过期时为 null */
  thumb_url: string | null
}

export interface HistoryListQuery {
  page?: number
  page_size?: number
  class_index?: number
  /** 起始时间戳（含） */
  start_ts?: number
  /** 结束时间戳（含） */
  end_ts?: number
  keyword?: string
}

/** `GET /api/history/{record_id}` 的返回 */
export interface RecordDetailOut {
  record: RecordItem
  candidates: Candidate[]
  species: Species | null
  /** 原图已过期或已删除时为 null → 触发 40402 区块级提示 */
  image: ImageAsset | null
}

export interface RecordDeleteIn {
  record_ids: string[]
}

export interface DeleteOut {
  deleted: number
}

/* ══════════════════════════════════════════════════════════════
   系统配置（管理端）
   ══════════════════════════════════════════════════════════════ */

export type ConfigValueType = 'int' | 'float' | 'str' | 'bool'

export interface ConfigItem {
  config_key: string
  /** 后端统一以字符串存储，前端按 `value_type` 解析 */
  value: string
  value_type: ConfigValueType
  description: string | null
  updated_at: number
}

export interface ConfigUpdateIn {
  value: string
}

/** 已知配置键（`GET /api/admin/config` 实测返回 5 项） */
export const CONFIG_KEYS = {
  GUEST_QUOTA: 'guest_quota',
  BATCH_UPLOAD_LIMIT: 'batch_upload_limit',
  MAX_FILE_SIZE_MB: 'max_file_size_mb',
  IMAGE_RETENTION_DAYS: 'image_retention_days',
  LOW_CONFIDENCE_THRESHOLD: 'low_confidence_threshold',
} as const

/* ══════════════════════════════════════════════════════════════
   管理端统计与日志
   ══════════════════════════════════════════════════════════════ */

export interface TopSpeciesItem {
  cn_name: string
  class_index: number
  count: number
}

export interface AdminStats {
  total_users: number
  active_users: number
  total_records: number
  total_uploads: number
  records_today: number
  top_species: TopSpeciesItem[]
  avg_duration_ms: number
}

export interface OperationLog {
  id: number
  /** 游客操作或用户已删除时为 null */
  user_id: number | null
  action: string
  target_type: string | null
  target_id: string | null
  ip: string | null
  detail: string | null
  created_at: number
}

/* ══════════════════════════════════════════════════════════════
   系统状态
   ══════════════════════════════════════════════════════════════ */

export interface HealthOut {
  status: string
  ready: boolean
  device: string
  model_version: string | null
  uptime_s: number
  database: string
}

export interface ModelInfo {
  num_classes: number
  img_size: number
  device: string
  ready: boolean
  model_version: string
  trained_epoch: number
  trained_metrics: {
    accuracy: number
    macro_precision: number
    macro_recall: number
    macro_f1: number
    weighted_f1: number
    per_class_f1: number[]
    per_class_precision: number[]
    per_class_recall: number[]
  } | null
}
