/**
 * 格式化工具
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §3.6「应实现为工具函数的格式器」
 *
 * 【强制纪律 D-02】置信度与概率**禁止各页面自行 `toFixed`**，
 * 一律经本文件的 `formatPercent` / `formatPercentTiny`。
 * ────────────────────────────────────────────────────────────────
 */

/**
 * 置信度 / 概率 → 百分比字符串，保留 1 位小数（D-02）。
 * @example formatPercent(0.621) // '62.1%'
 */
export function formatPercent(v: number, digits = 1): string {
  if (!Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

/**
 * 极小概率 → 「< 0.1%」（D-03）。
 * 四舍五入后为 0.0% 时不得显示 0.0%，须显示「< 0.1%」。
 * @example formatPercentTiny(0.0004) // '< 0.1%'
 */
export function formatPercentTiny(v: number, digits = 1): string {
  if (!Number.isFinite(v)) return '—'
  const t = Number((v * 100).toFixed(digits))
  if (t <= 0 && v > 0) return '< 0.1%'
  if (v === 0) return '0.0%'
  return `${t.toFixed(digits)}%`
}

/**
 * 概率 → 百分比（自动处理极小值）。
 * 页面展示置信度统一用此函数，不必自行判断。
 */
export function formatConfidence(v: number): string {
  if (!Number.isFinite(v)) return '—'
  if (v > 0 && v < 0.0005) return formatPercentTiny(v)
  return formatPercent(v)
}

/**
 * 耗时 → 整数毫秒（D-04）。
 * @example formatDuration(1843) // '1843 ms'
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return '—'
  return `${Math.round(ms)} ms`
}

/**
 * Unix 时间戳（秒，UTC）→ `YYYY-MM-DD HH:mm:ss`，展示层转 UTC+8（D-05）。
 * 对齐 BR-HISTORY-08。
 */
export function formatDateTime(ts: number | null | undefined): string {
  if (ts == null || !Number.isFinite(ts)) return '—'
  // 时间戳为秒，Date 需毫秒
  const d = new Date(ts * 1000)
  const p = (n: number, len = 2) => String(n).padStart(len, '0')
  // 用 UTC+8 偏移量计算，避免依赖运行环境时区
  const cst = new Date(d.getTime() + 8 * 3600 * 1000)
  return (
    `${cst.getUTCFullYear()}-${p(cst.getUTCMonth() + 1)}-${p(cst.getUTCDate())} ` +
    `${p(cst.getUTCHours())}:${p(cst.getUTCMinutes())}:${p(cst.getUTCSeconds())}`
  )
}

/** Unix 时间戳（秒）→ `YYYY-MM-DD`（UTC+8），用于筛选器与日期列 */
export function formatDate(ts: number | null | undefined): string {
  const full = formatDateTime(ts)
  return full === '—' ? full : full.slice(0, 10)
}

/**
 * Top-K 候选 → 单行摘要，供 CSV 导出第 6 列（D9 §3.6）。
 * **分隔符为竖线**（CSV 中须转义，见 §5.6）。
 * @example formatTop5Summary([{cn_name:'A',confidence:0.621},...])
 *          // 'A:62.1% | B:18.3% | ...'
 */
export function formatTop5Summary(
  arr: Array<{ cn_name: string; confidence: number }>,
): string {
  return arr.map((c) => `${c.cn_name}:${formatPercent(c.confidence)}`).join(' | ')
}

/** 文件体积 → 人类可读。用于上传队列角标与图片元信息 */
export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

/** 数字 → 千分位。用于管理端统计卡 */
export function formatNumber(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—'
  return n.toLocaleString('zh-CN')
}

/**
 * 相对时间（「3 分钟前」）。
 * 仅用于列表的时间辅助说明；主时间列仍用 {@link formatDateTime}。
 */
export function formatRelative(ts: number | null | undefined, nowMs = Date.now()): string {
  if (ts == null || !Number.isFinite(ts)) return '—'
  const diff = Math.floor(nowMs / 1000) - ts
  if (diff < 0) return '刚刚'
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} 天前`
  return formatDate(ts)
}

/** 秒数 → 「n 分钟」文案（用于 40105 账号锁定的占位符） */
export function secondsToMinutes(seconds: number): number {
  return Math.max(1, Math.ceil(seconds / 60))
}

/** 截断字符串并加省略号（列表单元格用） */
export function truncate(s: string | null | undefined, max = 24): string {
  if (!s) return '—'
  return s.length > max ? `${s.slice(0, max)}…` : s
}
