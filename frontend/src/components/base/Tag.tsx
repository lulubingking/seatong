/**
 * C-16 Tag —— 状态胶囊
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §4.2 C-16
 *
 * 局部圆角 `999px`（D9 §3.8「局部值」，不占用圆角令牌）。
 * 【纪律 R-01～R-04】语义色成组使用：`-50` 底 + 主色文字。
 * 【纪律 §8.3.5】色彩以外须有信息通道 —— 胶囊内文字本身即通道。
 * ────────────────────────────────────────────────────────────────
 */

import type { ReactNode } from 'react'

export type TagTone = 'brand' | 'ok' | 'warn' | 'danger' | 'accent' | 'muted'

/** 色值成组取自令牌族，不写十六进制字面量（N-03 纪律） */
const TONE: Record<TagTone, { bg: string; fg: string }> = {
  brand: { bg: 'var(--primary-50)', fg: 'var(--primary-600)' },
  ok: { bg: 'var(--success-50)', fg: 'var(--success)' },
  warn: { bg: 'var(--warn-50)', fg: 'var(--warn)' },
  danger: { bg: 'var(--danger-50)', fg: 'var(--danger)' },
  accent: { bg: 'var(--accent-50)', fg: 'var(--accent)' },
  muted: { bg: 'var(--surface-3)', fg: 'var(--text-2)' },
}

export interface TagProps {
  tone?: TagTone
  children: ReactNode
  className?: string
  /** 前置圆点（用于状态类，提供色彩以外的第二个通道） */
  dot?: boolean
}

export default function Tag({ tone = 'muted', children, className = '', dot = false }: TagProps) {
  const t = TONE[tone]
  return (
    <span
      className={[
        'inline-flex items-center gap-1.5 px-2 py-[3px] text-[12px] font-medium leading-[1.4] whitespace-nowrap',
        className,
      ].join(' ')}
      style={{ background: t.bg, color: t.fg, borderRadius: 'var(--radius-pill)' }}
    >
      {dot && (
        <span
          aria-hidden="true"
          style={{ width: 5, height: 5, borderRadius: '50%', background: 'currentColor', flexShrink: 0 }}
        />
      )}
      {children}
    </span>
  )
}
