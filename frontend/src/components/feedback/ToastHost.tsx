/**
 * C-32 Toast 宿主
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §4.4 C-32（Toast）、§7.1（状态反馈规范）、§3.8（z-index 300）
 *
 * 规格：
 *   · 位置：右下角（桌面）/ 底部居中（移动端）
 *   · 最高浮层 `z-index: 300`
 *   · 全站**两处阴影之一**：`0 4px 14px rgba(15,23,42,.09)`
 *   · 自动消失：默认 3 s，网络类 5 s
 *   · 动效：进出场仅用 transform / opacity；尊重 `prefers-reduced-motion`
 *   · 无障碍：容器 `aria-live="polite"`，错误类用 `role="alert"`
 * ────────────────────────────────────────────────────────────────
 */

import { useUiStore, type ToastTone } from '@/stores/uiStore'
import { useBreakpoint } from '@/hooks/useBreakpoint'

const TONE_STYLE: Record<ToastTone, { bg: string; border: string; fg: string; icon: JSX.Element }> = {
  info: {
    bg: 'var(--accent-50)',
    border: 'var(--accent-border)',
    fg: 'var(--accent)',
    icon: <InfoIcon />,
  },
  ok: {
    bg: 'var(--success-50)',
    border: 'var(--success-border)',
    fg: 'var(--success)',
    icon: <CheckIcon />,
  },
  warn: {
    bg: 'var(--warn-50)',
    border: 'var(--warn-border)',
    fg: 'var(--warn)',
    icon: <WarnIcon />,
  },
  danger: {
    bg: 'var(--danger-50)',
    border: 'var(--danger-border)',
    fg: 'var(--danger)',
    icon: <WarnIcon />,
  },
}

export default function ToastHost() {
  const toasts = useUiStore((s) => s.toasts)
  const dismiss = useUiStore((s) => s.dismissToast)
  const { isMobile } = useBreakpoint()

  if (toasts.length === 0) return null

  return (
    <div
      aria-live="polite"
      className={[
        'fixed z-toast flex flex-col gap-2 pointer-events-none',
        isMobile ? 'left-1/2 -translate-x-1/2 bottom-5 w-[min(92vw,420px)]' : 'right-5 bottom-5 w-[360px]',
      ].join(' ')}
    >
      {toasts.map((t) => {
        const s = TONE_STYLE[t.tone]
        return (
          <div
            key={t.id}
            role={t.tone === 'danger' ? 'alert' : 'status'}
            className="pointer-events-auto flex items-start gap-2.5 rounded-lg border px-3.5 py-3 toast-enter"
            style={{
              background: s.bg,
              borderColor: s.border,
              // 全站两处阴影之一（D9 §3.8）
              boxShadow: 'var(--shadow-toast)',
            }}
          >
            <span aria-hidden="true" className="mt-0.5 shrink-0" style={{ color: s.fg }}>
              {s.icon}
            </span>
            <p className="flex-1 m-0 text-[13.5px] leading-[1.5]" style={{ color: s.fg }}>
              {t.message}
            </p>
            <button
              type="button"
              aria-label="关闭提示"
              onClick={() => dismiss(t.id)}
              className="shrink-0 mt-0.5 p-0.5 rounded-sm border-0 bg-transparent opacity-60 hover:opacity-100"
              style={{ color: s.fg }}
            >
              <CloseIcon />
            </button>
          </div>
        )
      })}
    </div>
  )
}

/* ── 内联图标（D9 §3.10 图标纪律：viewBox 24、stroke-width 1.9、继承 currentColor）── */

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path d="M20 6.5 9.5 17 4 11.5" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function WarnIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path d="M12 3.8 21.2 20H2.8L12 3.8Z" stroke="currentColor" strokeWidth="1.9" strokeLinejoin="round" />
      <path d="M12 10v4.2" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <circle cx="12" cy="17.2" r="1" fill="currentColor" />
    </svg>
  )
}

function InfoIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.9" />
      <path d="M12 11v5.5" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      <circle cx="12" cy="7.8" r="1" fill="currentColor" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  )
}
