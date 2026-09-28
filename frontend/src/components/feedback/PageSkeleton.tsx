/**
 * L1 区块级骨架屏
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §7.1.1（加载态分级 —— L1 区块级）、§10.3.3
 *
 * 【纪律 M-05】加载态**不得只有 Spinner**（无信息量、无法预判布局）。
 * 骨架屏须模拟真实内容的结构，让用户预判即将出现什么。
 *
 * 本组件用于：
 *   · 路由懒加载的 Suspense fallback
 *   · 页面内区块的初次加载
 * ────────────────────────────────────────────────────────────────
 */

interface Props {
  /** 骨架行数（表格/列表场景） */
  rows?: number
  /** 是否展示顶部标题条 */
  showHeader?: boolean
  /** 变体：card 卡片网格 / list 列表 / table 表格 */
  variant?: 'list' | 'card' | 'table'
}

export default function PageSkeleton({ rows = 5, showHeader = true, variant = 'list' }: Props) {
  return (
    <div className="animate-pulse" aria-busy="true" aria-live="polite">
      <span className="sr-only">加载中</span>

      {showHeader && (
        <div className="mb-5">
          <Bar w="32%" h={20} className="mb-2.5" />
          <Bar w="56%" h={13} />
        </div>
      )}

      {variant === 'card' && (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="rounded-lg border border-line bg-surface p-4">
              <Bar w="70%" h={15} className="mb-3" />
              <Bar w="100%" h={11} className="mb-2" />
              <Bar w="88%" h={11} className="mb-2" />
              <Bar w="52%" h={11} />
            </div>
          ))}
        </div>
      )}

      {variant === 'table' && (
        <div className="rounded-lg border border-line bg-surface overflow-hidden">
          <div className="px-4 py-3 border-b border-line bg-surface-2">
            <Bar w="26%" h={13} />
          </div>
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="px-4 py-3 flex items-center gap-4 border-b border-line last:border-b-0">
              <Bar w={44} h={44} radius="var(--radius)" />
              <Bar w="20%" h={13} />
              <Bar w="14%" h={13} />
              <div className="flex-1" />
              <Bar w={64} h={13} />
            </div>
          ))}
        </div>
      )}

      {variant === 'list' && (
        <div className="flex flex-col gap-2.5">
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="rounded-lg border border-line bg-surface px-4 py-3.5 flex items-center gap-4">
              <Bar w={40} h={40} radius="var(--radius)" />
              <div className="flex-1">
                <Bar w="38%" h={14} className="mb-2" />
                <Bar w="62%" h={11} />
              </div>
              <Bar w={60} h={13} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Bar({
  w,
  h,
  className = '',
  radius = 'var(--radius-sm)',
}: {
  w: number | string
  h: number
  className?: string
  radius?: string
}) {
  return (
    <div
      className={className}
      style={{
        width: typeof w === 'number' ? `${w}px` : w,
        height: `${h}px`,
        borderRadius: radius,
        background: 'var(--surface-3)',
      }}
    />
  )
}
