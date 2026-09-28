/**
 * UI 状态 store
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §10.5（状态管理约定）—— 抽屉开合、Toast 队列、全局 loading 计数
 *
 * Toast 自研（C-32）而非用 AntD message 的原因：
 *   需要队列化、需要 5 s 自动消失、需要遵守 `prefers-reduced-motion`。
 *   AntD 的 message 在多条并发时定位与时长控制不符合 §7.1 的状态反馈规范。
 * ────────────────────────────────────────────────────────────────
 */

import { create } from 'zustand'

export type ToastTone = 'info' | 'ok' | 'warn' | 'danger'

export interface ToastItem {
  id: number
  tone: ToastTone
  message: string
  /** 毫秒。NET-01 要求 5 s，其余默认 3 s */
  duration: number
}

let toastSeq = 0

export interface UiState {
  /** 移动端抽屉导航开合（D9 §8.2） */
  drawerOpen: boolean
  toasts: ToastItem[]
  /** 全局 loading 计数（并发请求累加，归零才隐藏遮罩） */
  loadingCount: number

  openDrawer: () => void
  closeDrawer: () => void
  toggleDrawer: () => void

  /** 压入一条 Toast，返回其 id（可手动 dismiss） */
  toast: (message: string, tone?: ToastTone, duration?: number) => number
  dismissToast: (id: number) => void
  clearToasts: () => void

  beginLoading: () => void
  endLoading: () => void
}

export const useUiStore = create<UiState>((set, get) => ({
  drawerOpen: false,
  toasts: [],
  loadingCount: 0,

  openDrawer: () => set({ drawerOpen: true }),
  closeDrawer: () => set({ drawerOpen: false }),
  toggleDrawer: () => set((s) => ({ drawerOpen: !s.drawerOpen })),

  toast(message, tone = 'info', duration = 3000) {
    const id = ++toastSeq
    set((s) => ({ toasts: [...s.toasts, { id, tone, message, duration }] }))
    if (duration > 0) {
      window.setTimeout(() => {
        // 组件可能已卸载，用 get 检测避免无谓 set
        if (get().toasts.some((t) => t.id === id)) {
          set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
        }
      }, duration)
    }
    return id
  },

  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  clearToasts: () => set({ toasts: [] }),

  beginLoading: () => set((s) => ({ loadingCount: s.loadingCount + 1 })),
  endLoading: () => set((s) => ({ loadingCount: Math.max(0, s.loadingCount - 1) })),
}))

/* ── 便捷函数（非钩子场景，如拦截器、api 回调）──────────────── */

export const toast = (m: string, tone: ToastTone = 'info', duration?: number): number =>
  useUiStore.getState().toast(m, tone, duration)

export const toastOk = (m: string, duration?: number) => toast(m, 'ok', duration)
export const toastWarn = (m: string, duration?: number) => toast(m, 'warn', duration)
export const toastError = (m: string, duration?: number) => toast(m, 'danger', duration)
