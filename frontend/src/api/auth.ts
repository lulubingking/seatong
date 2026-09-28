/**
 * 认证接口 —— `/api/auth/*`（4 个端点）
 * 来源：后端 openapi 实测
 */

import { http } from './client'
import { ENDPOINTS } from './index'
import type { LoginIn, LoginOut, RefreshIn, RegisterIn, User } from './types'

/** POST /api/auth/register —— 注册后**不自动登录**，须跳转登录页 */
export function register(body: RegisterIn): Promise<User> {
  return http.post<User>(ENDPOINTS.register, body)
}

/** POST /api/auth/login */
export function login(body: LoginIn): Promise<LoginOut> {
  return http.post<LoginOut>(ENDPOINTS.login, body)
}

/** POST /api/auth/refresh —— 用 refresh_token 换新 access_token */
export function refresh(body: RefreshIn): Promise<LoginOut> {
  return http.post<LoginOut>(ENDPOINTS.refresh, body)
}

/** POST /api/auth/logout —— 服务端吊销当前令牌 */
export function logout(): Promise<null> {
  return http.post<null>(ENDPOINTS.logout)
}
