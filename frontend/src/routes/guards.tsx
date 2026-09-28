/**
 * 路由守卫
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §10.3.2（守卫实现规则）、§2.2（访问权限列）
 *
 * 三条规则：
 *   1. 认证守卫 —— 未登录访问 `requiresAuth` 路由 → 跳 `/login?redirect=<当前路径>`
 *   2. 角色守卫 —— 角色不符 → **渲染 NotFound 视图**（而非跳转；
 *      依据 §6.3「不暴露管理入口存在性」—— 让非管理员无法判断
 *      `/admin/*` 是「不存在」还是「无权限」）
 *   3. 反向门禁 —— 已登录访问 `/login` `/register` → 跳首页
 *
 * 【重定向白名单】`?redirect=` 仅接受以 `/` 开头且不以 `//` 开头的站内路径，
 * 否则回首页（防开放重定向漏洞）。
 * ────────────────────────────────────────────────────────────────
 */

import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { PATHS } from './paths'

/** 校验重定向目标是否为安全的站内路径 */
export function safeRedirect(raw: string | null | undefined, fallback = PATHS.home): string {
  if (!raw) return fallback
  // 必须以单个 `/` 开头；`//evil.com` 是协议相对 URL，须拒绝
  if (!raw.startsWith('/') || raw.startsWith('//')) return fallback
  return raw
}

export interface GuardProps {
  children: ReactNode
  /** 要求已登录 */
  requiresAuth?: boolean
  /** 要求管理员角色 */
  requiresAdmin?: boolean
  /** 已登录时访问则重定向首页（登录/注册页用） */
  guestOnly?: boolean
  /**
   * 角色不符时渲染的元素（通常是 NotFound 页面）。
   * 由路由表注入，避免本模块反向 import 页面组件造成循环依赖。
   */
  forbiddenFallback?: ReactNode
}

/**
 * 通用守卫组件。包裹单个路由元素使用。
 *
 * 【重要】会话未确认（`resolved=false`）时**不得**立即判定为未登录 ——
 * 应用启动瞬间 `GET /users/me` 尚未返回，若此时跳登录页会造成
 * 带 token 的用户被误踢。故由上层 `App` 在 bootstrap 完成后才挂载路由。
 */
export function RouteGuard({
  children,
  requiresAuth = false,
  requiresAdmin = false,
  guestOnly = false,
  forbiddenFallback = null,
}: GuardProps) {
  const location = useLocation()
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)
  const isLoggedIn = token !== null && user !== null

  // ① 反向门禁：已登录访问登录/注册页 → 首页
  if (guestOnly && isLoggedIn) {
    return <Navigate to={PATHS.home} replace />
  }

  // ② 认证守卫
  if (requiresAuth && !isLoggedIn) {
    const redirect = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`${PATHS.login}?redirect=${redirect}`} replace />
  }

  // ③ 角色守卫 —— 渲染 404 而非跳转（不暴露管理入口存在性）
  if (requiresAdmin && user?.role !== 'admin') {
    return <>{forbiddenFallback}</>
  }

  return <>{children}</>
}
