/**
 * 会话状态 store
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §6.3（登录与会话恢复时序）、§10.5（状态管理约定）
 *
 * 持有：token、当前用户、角色、游客额度
 *
 * 【关键设计】令牌失效时**不跳转**登录页 —— 置为游客态 + Toast 轻提示，
 * 仅在用户试图执行**写操作**时才弹出登录引导（D9 §10.3.2）。
 * 这避免了「登录页反复弹出」的死循环。
 * ────────────────────────────────────────────────────────────────
 */

import { create } from 'zustand'
import * as authApi from '@/api/auth'
import * as usersApi from '@/api/users'
import { getGuestSessionId } from '@/api/client'
import { USER_ROLE, type UserRole } from '@/constants/enums'
import type { GuestQuota, User } from '@/api/types'

const LS_ACCESS = 'seatong.access_token'
const LS_REFRESH = 'seatong.refresh_token'
const LS_USER = 'seatong.user'

function safeGet(k: string): string | null {
  try {
    return window.localStorage.getItem(k)
  } catch {
    return null
  }
}
function safeSet(k: string, v: string): void {
  try {
    window.localStorage.setItem(k, v)
  } catch {
    /* 忽略 */
  }
}
function safeDel(k: string): void {
  try {
    window.localStorage.removeItem(k)
  } catch {
    /* 忽略 */
  }
}

export interface AuthState {
  /* ── 状态 ── */
  /** access token，null = 游客 */
  token: string | null
  refreshToken: string | null
  user: User | null
  /** 会话是否已从后端确认（启动时为 false，`GET /users/me` 返回后置 true） */
  resolved: boolean
  /** 游客额度状态（后端 `GET /users/me` 内联返回） */
  guestQuota: GuestQuota | null
  /** 登录引导弹窗是否打开（由写操作触发的 40101 / 42901 打开） */
  loginPromptOpen: boolean
  /** 引导弹窗的说明文案 */
  loginPromptReason: string

  /* ── 派生 ── */
  isLoggedIn: () => boolean
  isAdmin: () => boolean

  /* ── 动作 ── */
  /** 应用启动时调用：若有 token 则拉取 me；否则以游客身份拉取额度 */
  bootstrap: () => Promise<void>
  login: (username: string, password: string) => Promise<void>
  register: (username: string, password: string, nickname?: string, email?: string) => Promise<void>
  logout: () => Promise<void>
  /** 令牌失效处理（由 client 拦截器回调）—— 清 token 并降级游客态 */
  handleUnauthorized: (code: string) => void
  /** 刷新额度（任何非 50002 的错误后须主动调用 —— D9 §7.3.6 纪律 3） */
  refreshQuota: () => Promise<void>
  /** 扣减本地额度（乐观更新；随后仍会 refreshQuota 校准） */
  consumeQuota: () => void
  openLoginPrompt: (reason: string) => void
  closeLoginPrompt: () => void
  setUser: (u: User) => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: safeGet(LS_ACCESS),
  refreshToken: safeGet(LS_REFRESH),
  user: (() => {
    const raw = safeGet(LS_USER)
    if (!raw) return null
    try {
      return JSON.parse(raw) as User
    } catch {
      return null
    }
  })(),
  resolved: false,
  guestQuota: null,
  loginPromptOpen: false,
  loginPromptReason: '',

  isLoggedIn: () => get().token !== null && get().user !== null,
  isAdmin: () => get().user?.role === USER_ROLE.ADMIN,

  async bootstrap() {
    const token = get().token
    if (token) {
      try {
        const { user, guest_quota } = await usersApi.getMe()
        if (user) {
          set({ user, guestQuota: guest_quota, resolved: true })
          safeSet(LS_USER, JSON.stringify(user))
          return
        }
        // token 存在但服务端不认（已过期/已登出）→ 静默降级为游客
        set({ token: null, refreshToken: null, user: null })
        safeDel(LS_ACCESS)
        safeDel(LS_REFRESH)
        safeDel(LS_USER)
      } catch {
        // 网络异常时**不清 token**，保留本地会话，待下次请求重试
        set({ resolved: true })
        return
      }
    }
    // 游客：先确保会话 ID 已持久化，再拉取额度
    getGuestSessionId()
    try {
      const { guest_quota } = await usersApi.getMe()
      set({ guestQuota: guest_quota, resolved: true })
    } catch {
      set({ resolved: true })
    }
  },

  async login(username, password) {
    const out = await authApi.login({ username, password })
    safeSet(LS_ACCESS, out.access_token)
    safeSet(LS_REFRESH, out.refresh_token)
    safeSet(LS_USER, JSON.stringify(out.user))
    set({
      token: out.access_token,
      refreshToken: out.refresh_token,
      user: out.user,
      resolved: true,
      // 登录后额度概念消失（登录用户不限次）
      guestQuota: null,
      loginPromptOpen: false,
      loginPromptReason: '',
    })
  },

  async register(username, password, nickname, email) {
    // 注册后**不自动登录**（后端行为），由页面跳转登录页
    await authApi.register({ username, password, nickname, email })
  },

  async logout() {
    try {
      await authApi.logout()
    } catch {
      // 服务端吊销失败不阻塞本地登出
    }
    safeDel(LS_ACCESS)
    safeDel(LS_REFRESH)
    safeDel(LS_USER)
    set({ token: null, refreshToken: null, user: null, guestQuota: null })
    // 登出后回到游客身份，重新拉取游客额度
    await get().refreshQuota()
  },

  handleUnauthorized(code) {
    safeDel(LS_ACCESS)
    safeDel(LS_REFRESH)
    safeDel(LS_USER)
    set({
      token: null,
      refreshToken: null,
      user: null,
      loginPromptReason: code === '40102' ? '登录状态已过期，请重新登录' : '请先登录后再操作',
    })
  },

  async refreshQuota() {
    if (get().token) return // 登录用户无额度概念
    getGuestSessionId()
    try {
      const { guest_quota } = await usersApi.getMe()
      set({ guestQuota: guest_quota })
    } catch {
      /* 额度刷新失败不阻断主流程 */
    }
  },

  consumeQuota() {
    const q = get().guestQuota
    if (!q || !q.is_guest) return
    set({
      guestQuota: {
        ...q,
        used: q.used + 1,
        remaining: Math.max(0, q.remaining - 1),
        known: true,
      },
    })
  },

  openLoginPrompt(reason) {
    set({ loginPromptOpen: true, loginPromptReason: reason })
  },
  closeLoginPrompt() {
    set({ loginPromptOpen: false })
  },
  setUser(u) {
    safeSet(LS_USER, JSON.stringify(u))
    set({ user: u })
  },
}))

/* ── 非 React 环境下的读取（供 client 拦截器装配）───────────── */

export function getTokenSync(): string | null {
  return useAuthStore.getState().token
}

export function onUnauthorizedSync(code: string): void {
  useAuthStore.getState().handleUnauthorized(code)
  // 仅记录意图，**不跳转** —— 由页面在需要时读取 loginPromptOpen 自行处理
  if (code === '40101' || code === '42901') {
    useAuthStore.getState().openLoginPrompt(
      code === '42901' ? '试用次数已用完，登录后可继续使用' : '请先登录后再操作',
    )
  }
}

/** 当前角色（未登录返回 null） */
export function currentRole(): UserRole | null {
  return useAuthStore.getState().user?.role ?? null
}
