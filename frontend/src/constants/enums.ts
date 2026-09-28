/**
 * 枚举与联合类型
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：
 *   · D7（数据库设计）—— 状态取值
 *   · D9 §6.1（识别作业状态机）、§4.2 C-16（状态胶囊）、§5.6（历史列表）
 *
 * 纪律：取值字符串必须与后端**逐字符一致**（D9 §10.4.5 —— 保持 snake_case，
 * 不做 camelCase 转换）。本文件是前端唯一枚举来源。
 * ────────────────────────────────────────────────────────────────
 */

/* ══════════════════════════════════════════════════════════════
   识别作业状态机（D9 §6.1）
   —— recognizeStore 的 `phase` 字段，单一字段驱动，不得用多个布尔拼凑
   ══════════════════════════════════════════════════════════════ */

export const JOB_PHASE = {
  /** 空闲：无待处理文件 */
  IDLE: 'idle',
  /** 已选文件，等待用户点击「开始识别」 */
  READY: 'ready',
  /** 上传中（并发池 ≤3） */
  UPLOADING: 'uploading',
  /** 部分文件上传失败，其余可继续 */
  UPLOAD_FAILED: 'upload_failed',
  /** 推理中 */
  RECOGNIZING: 'recognizing',
  /** 全部成功，展示结果 */
  DONE: 'done',
  /** 部分成功（批量场景，逐张结果混合） */
  PARTIAL: 'partial',
  /** 整体失败 */
  FAILED: 'failed',
} as const

export type JobPhase = typeof JOB_PHASE[keyof typeof JOB_PHASE]

/** 单个文件的处理状态 */
export const FILE_STATUS = {
  PENDING: 'pending',
  UPLOADING: 'uploading',
  UPLOADED: 'uploaded',
  FAILED: 'failed',
  RECOGNIZING: 'recognizing',
  DONE: 'done',
} as const

export type FileStatus = typeof FILE_STATUS[keyof typeof FILE_STATUS]

/* ══════════════════════════════════════════════════════════════
   识别记录状态（D7：`recognition_record.status`）
   注意：仅两个取值，与 D7 的 CHECK 约束一致
   ══════════════════════════════════════════════════════════════ */

export const RECORD_STATUS = {
  SUCCESS: 'success',
  INTERRUPTED: 'interrupted',
} as const

export type RecordStatus = typeof RECORD_STATUS[keyof typeof RECORD_STATUS]

/** 记录状态的展示标签与胶囊变体（D9 §4.2 C-16） */
export const RECORD_STATUS_META: Record<RecordStatus, { label: string; tone: 'ok' | 'warn' }> = {
  success: { label: '识别成功', tone: 'ok' },
  interrupted: { label: '已中断', tone: 'warn' },
}

/* ══════════════════════════════════════════════════════════════
   用户角色（D7：`user.role`；PRD 决策基线「设管理员角色」）
   ══════════════════════════════════════════════════════════════ */

export const USER_ROLE = {
  USER: 'user',
  ADMIN: 'admin',
} as const

export type UserRole = typeof USER_ROLE[keyof typeof USER_ROLE]

/* ══════════════════════════════════════════════════════════════
   用户账号状态（D7：`user.status` 为 INTEGER 0/1，非布尔、非字符串）
   ══════════════════════════════════════════════════════════════ */

export const USER_STATUS = {
  DISABLED: 0,
  ACTIVE: 1,
} as const

export type UserStatus = typeof USER_STATUS[keyof typeof USER_STATUS]

export const USER_STATUS_META: Record<number, { label: string; tone: 'ok' | 'muted' }> = {
  [USER_STATUS.ACTIVE]: { label: '正常', tone: 'ok' },
  [USER_STATUS.DISABLED]: { label: '已禁用', tone: 'muted' },
}

/* ══════════════════════════════════════════════════════════════
   置信度分档（D9 §5.2 / §5.7 —— 结果区与详情页的解读提示）
   —— 用于决定是否展示「结果仅供参考」的强化提示
   ══════════════════════════════════════════════════════════════ */

export const CONFIDENCE_TIER = {
  /** ≥ 0.85 —— 与 PRD 准确率目标对齐 */
  HIGH: 'high',
  /** 0.60 ～ 0.85 —— 可参考，建议核对 Top-5 */
  MEDIUM: 'medium',
  /** < 0.60 —— 明确提示可信度有限 */
  LOW: 'low',
} as const

export type ConfidenceTier = typeof CONFIDENCE_TIER[keyof typeof CONFIDENCE_TIER]

/** 置信度分档阈值 */
export const CONFIDENCE_THRESHOLD = {
  HIGH: 0.85,
  MEDIUM: 0.6,
} as const

export const CONFIDENCE_TIER_META: Record<
  ConfidenceTier,
  { label: string; tone: 'ok' | 'accent' | 'warn'; hint: string }
> = {
  high: { label: '高置信度', tone: 'ok', hint: '模型对本次判定较为确定' },
  medium: { label: '中等置信度', tone: 'accent', hint: '建议结合 Top-5 候选一并参考' },
  low: { label: '低置信度', tone: 'warn', hint: '可信度有限，建议更换更清晰的图片重试' },
}

export function toConfidenceTier(v: number): ConfidenceTier {
  if (v >= CONFIDENCE_THRESHOLD.HIGH) return CONFIDENCE_TIER.HIGH
  if (v >= CONFIDENCE_THRESHOLD.MEDIUM) return CONFIDENCE_TIER.MEDIUM
  return CONFIDENCE_TIER.LOW
}

/* ══════════════════════════════════════════════════════════════
   设备断点（D9 §8.1）
   ══════════════════════════════════════════════════════════════ */

export const BREAKPOINT = {
  XS: 'xs',
  SM: 'sm',
  MD: 'md',
  LG: 'lg',
} as const

export type Breakpoint = typeof BREAKPOINT[keyof typeof BREAKPOINT]

/* ══════════════════════════════════════════════════════════════
   记录排序字段（D9 §5.6 历史列表）
   ══════════════════════════════════════════════════════════════ */

export const SORT_ORDER = {
  DESC: 'desc',
  ASC: 'asc',
} as const

export type SortOrder = typeof SORT_ORDER[keyof typeof SORT_ORDER]
