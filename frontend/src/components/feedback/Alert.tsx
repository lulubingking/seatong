/**
 * C-31 Alert —— 提示条
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §4.4 C-31、§3.5（语义色四件套）
 *
 * 【纪律 R-01～R-04】语义色必须成组使用：
 *   `-50` 底 + `-border` 边 + 主色文字。不得只用一种。
 * 【纪律】不得纯装饰 —— 语义色必须承载「信息 / 成功 / 警告 / 危险」之一。
 *
 * 【对比度说明（D9 §8.3.2 ②）】两边框令牌对白底仅 1.24 / 1.46:1，
 * 远低于 WCAG 3:1 → **边框不得作为唯一状态指示**。故本组件
 * 必须同时具备：图标 + 文字色差 + 背景色差，三重冗余通道。
 * ────────────────────────────────────────────────────────────────
 */

import type { ReactNode } from 'react'

export type AlertTone = 'info' | 'ok' | 'warn' | 'danger'

export interface AlertProps {
  tone?: AlertTone
  /** 标题（可选）。无标题时仅一行正文 */
  title?: ReactNode
  children?: ReactNode
  /** 右侧操作（如重试按钮）。**注意**：`retryable=false` 的错误不得提供 */
  action?: ReactNode
  className?: string
}

const TONE = {
  info: { bg: 'var(--accent-50)', border: 'var(--accent-border)', fg: 'var(--accent)', icon: IconInfo },
  ok: { bg: 'var(--success-50)', border: 'var(--success-border)', fg: 'var(--success)', icon: IconCheck },
  warn: { bg: 'var(--warn-50)', border: 'var(--warn-border)', fg: 'var(--warn)', icon: IconWarn },
  danger: { bg: 'var(--danger-50)', border: 'var(--danger-border)', fg: 'var(--danger)', icon: IconWarn },
} as const

export default function Alert({
  tone = 'info',
  title,
  children,
  action,
  className = '',
}: AlertProps) {
  const t = TONE[tone]
  const Icon = t.icon

  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      className={['flex items-start gap-2.5 rounded border px-3.5 py-3', className].join(' ')}
      style={{ background: t.bg, borderColor: t.border }}
    >
      <span aria-hidden="true" className="mt-[1px] shrink-0" style={{ color: t.fg }}>
        <Icon />
      </span>
      <div className="flex-1 min-w-0">
        {title && (
          <p className="m-0 text-[13.5px] font-semibold" style={{ color: t.fg }}>
            {title}
          </p>
        )}
        {children && (
          <div
            className={[
              'text-[13px] leading-[1.6]',
              title ? 'mt-1' : '',
            ].join(' ')}
            style={{ color: title ? 'var(--text-2)' : t.fg }}
          >
            {children}
          </div>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}

/* ── 图标（viewBox 24 / stroke-width 1.9 / currentColor）── */

function IconInfo() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.9" />
      <path d="M12 11v5.5" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <circle cx="12" cy="7.8" r="1" fill="currentColor" />
    </svg>
  )
}

function IconCheck() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.9" />
      <path d="M8 12.4l2.8 2.8L16.4 9.6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function IconWarn() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path d="M12 3.8 21.2 20H2.8L12 3.8Z" stroke="currentColor" strokeWidth="1.9" strokeLinejoin="round" />
      <path d="M12 10v4.2" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <circle cx="12" cy="17.2" r="1" fill="currentColor" />
    </svg>
  )
}
