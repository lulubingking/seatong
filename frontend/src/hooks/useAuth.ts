/**
 * 认证便捷 hook（薄封装，逻辑仍在 authStore）
 * 唯一来源：D9 §10.5
 */

import { useAuthStore } from '@/stores/authStore'

export interface UseAuthResult {
  isLoggedIn: boolean
  isAdmin: boolean
  user: ReturnType<typeof useAuthStore.getState>['user']
  guestQuota: ReturnType<typeof useAuthStore.getState>['guestQuota']
  /** 游客剩余次数（已登录时返回 null —— 无额度概念） */
  guestRemaining: number | null
  /** 是否可以提交识别（游客额度门禁，D9 §6.2） */
  quotaAllows: boolean
}

export function useAuth(): UseAuthResult {
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)
  const guestQuota = useAuthStore((s) => s.guestQuota)
  const isLoggedIn = token !== null && user !== null

  return {
    isLoggedIn,
    isAdmin: user?.role === 'admin',
    user,
    guestQuota,
    guestRemaining: isLoggedIn ? null : (guestQuota?.remaining ?? null),
    quotaAllows: isLoggedIn || (guestQuota?.remaining ?? 0) > 0,
  }
}
