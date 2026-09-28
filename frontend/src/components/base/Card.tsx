/**
 * C-17 Card —— 卡片容器
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §4.2 C-17
 *
 * 视觉策略（D9 §3.8）：本项目采用**扁平化 + 边框分层**，
 * 卡片通过 `--border` 边框与 `--surface` 底色区分层级，**不使用阴影**。
 * 外层容器圆角 `--radius-lg`（14px）。
 * ────────────────────────────────────────────────────────────────
 */

import type { ReactNode } from 'react'

export interface CardProps {
  children: ReactNode
  /** 卡片标题（单行，语义为 h2/h3 由外部决定，此处仅视觉） */
  title?: ReactNode
  /** 标题右侧操作区 */
  extra?: ReactNode
  /** 标题下方的说明文字 */
  description?: ReactNode
  className?: string
  /** 内容区内边距。`none` 时由使用方自行控制（如表格贴边） */
  padding?: 'none' | 'sm' | 'md'
  /** 是否作为整卡可点击（加 hover 态）。给了 onClick 时自动启用 */
  onClick?: () => void
}

export default function Card({
  children,
  title,
  extra,
  description,
  className = '',
  padding = 'md',
  onClick,
}: CardProps) {
  const padCls = padding === 'none' ? '' : padding === 'sm' ? 'p-3.5' : 'p-5'
  const interactive = Boolean(onClick)

  return (
    <section
      className={[
        'rounded-lg border border-line bg-surface',
        interactive ? 'cursor-pointer transition-colors hover:border-line-strong' : '',
        className,
      ].join(' ')}
      onClick={onClick}
      // 可点击卡片必须可键盘到达（D9 §9.4.5）
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onClick?.()
              }
            }
          : undefined
      }
    >
      {(title || extra) && (
        <header className="flex items-start gap-3 px-5 pt-4 pb-3 border-b border-line">
          <div className="flex-1 min-w-0">
            {title && <h2 className="m-0 text-[15px] font-semibold text-ink truncate">{title}</h2>}
            {description && (
              <p className="m-0 mt-1 text-[12.5px] text-ink-2 leading-[1.55]">{description}</p>
            )}
          </div>
          {extra && <div className="shrink-0">{extra}</div>}
        </header>
      )}
      <div className={padCls}>{children}</div>
    </section>
  )
}
