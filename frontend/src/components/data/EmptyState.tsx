/**
 * C-29 EmptyState —— 空态
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §4.3 C-29、§9.4.3 评审清单
 *
 * 【硬约束】空态必须具备**三段式**：是什么 / 为什么 / 怎么做。
 * 只写「暂无数据」不合格 —— 用户无法判断是自己操作有误还是系统就这状态。
 * ────────────────────────────────────────────────────────────────
 */

import type { ReactNode } from 'react'

export interface EmptyStateProps {
  /** ① 是什么：一句话说明这里本该有什么 */
  title: string
  /** ② 为什么：当前为何为空（用户视角的原因，不是技术原因） */
  description?: string
  /** ③ 怎么做：主行动按钮 */
  action?: ReactNode
  /** 次要说明（如操作提示） */
  hint?: ReactNode
  /** 自定义插画；不传则用默认中性图标 */
  icon?: ReactNode
  /** 紧凑模式（用于卡片内区块，而非整页） */
  compact?: boolean
}

export default function EmptyState({
  title,
  description,
  action,
  hint,
  icon,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={[
        'flex flex-col items-center justify-center text-center',
        compact ? 'py-9 px-4' : 'py-14 px-6',
      ].join(' ')}
    >
      <div
        className="mb-3.5 flex items-center justify-center rounded-full"
        style={{
          width: compact ? 44 : 56,
          height: compact ? 44 : 56,
          background: 'var(--surface-3)',
          color: 'var(--text-3)',
        }}
        aria-hidden="true"
      >
        {icon ?? <DefaultIcon size={compact ? 20 : 24} />}
      </div>

      <p className="m-0 text-[14.5px] font-semibold text-ink">{title}</p>

      {description && (
        <p className="m-0 mt-1.5 max-w-[380px] text-[13px] text-ink-2 leading-[1.6]">
          {description}
        </p>
      )}

      {action && <div className="mt-4">{action}</div>}

      {hint && <div className="mt-3 text-[12.5px] text-ink-3">{hint}</div>}
    </div>
  )
}

function DefaultIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect x="3.2" y="4.8" width="17.6" height="14.4" rx="2.4" stroke="currentColor" strokeWidth="1.9" />
      <circle cx="8.6" cy="10" r="1.6" stroke="currentColor" strokeWidth="1.9" />
      <path d="M3.6 17.2 9 12.4l3.4 3 3.6-3.6 4.4 4.2" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
