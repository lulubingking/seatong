/**
 * 用户接口
 * ────────────────────────────────────────────────────────────────
 * 自助：`/api/users/me*`（3 个端点，D8 §5.5～5.7）
 * 管理端：`/api/admin/users*`（5 个端点，须 admin 角色；40301 守卫，D8 §9.1～9.3）
 *
 * 【命名纪律】管理端端点**带 admin 前缀**，与自助端点分属两个命名空间 ——
 * 前者操作"任意用户"，后者只操作"自己"。混在一起会让权限边界难以审计。
 *
 * 【方法纪律】改密码是 **PUT /api/users/me/password**（整体替换语义），
 * 不是 POST。`PATCH` 仅用于"部分更新资料"。
 * ────────────────────────────────────────────────────────────────
 */

import { http } from './client'
import { ENDPOINTS } from './index'
import type {
  AdminResetPasswordIn,
  AdminUserCreateIn,
  AdminUserUpdateIn,
  ChangePasswordIn,
  GuestQuotaOut,
  MeOut,
  Page,
  UpdateMeIn,
  User,
} from './types'

/* ── 自助 ────────────────────────────────────────────────────── */

/**
 * GET /api/users/me
 * 返回 `{user, is_guest, guest_quota}`。游客额度**内联在此**，
 * 便于首屏一次请求确定"我是谁 + 还能试几次"。
 * 如需单独刷新额度，用 {@link getGuestQuota}（`/api/guest/quota`）。
 */
export function getMe(): Promise<MeOut> {
  return http.get<MeOut>(ENDPOINTS.me)
}

/** PATCH /api/users/me —— 更新昵称 / 邮箱 */
export function updateMe(body: UpdateMeIn): Promise<User> {
  return http.patch<User>(ENDPOINTS.me, body)
}

/** PUT /api/users/me/password —— 修改自己的密码（整体替换语义） */
export function changeMyPassword(body: ChangePasswordIn): Promise<null> {
  return http.put<null>(ENDPOINTS.myPassword, body)
}

/* ── 游客额度 ────────────────────────────────────────────────── */

/**
 * GET /api/guest/quota —— 查询游客剩余试用次数（D8 §5.8）
 *
 * 已登录用户调用时返回三者均为 0（服务端保证），前端不必自行判断身份。
 * 响应类型见 {@link GuestQuotaOut}（字段名是 `limit`，与 `/api/users/me`
 * 内嵌的 `guest_quota.quota` 有意不同，见该类型注释）。
 */
export function getGuestQuota(): Promise<GuestQuotaOut> {
  return http.get<GuestQuotaOut>(ENDPOINTS.guestQuota)
}

/* ── 管理端 ──────────────────────────────────────────────────── */

export interface ListUsersQuery {
  page?: number
  page_size?: number
  keyword?: string
  role?: string
  status?: number
}

/** GET /api/admin/users */
export function listUsers(q: ListUsersQuery = {}): Promise<Page<User>> {
  return http.get<Page<User>>(ENDPOINTS.adminUsers, { params: q })
}

/** POST /api/admin/users */
export function createUser(body: AdminUserCreateIn): Promise<User> {
  return http.post<User>(ENDPOINTS.adminUsers, body)
}

/** PATCH /api/admin/users/{user_id} */
export function updateUser(userId: number, body: AdminUserUpdateIn): Promise<User> {
  return http.patch<User>(ENDPOINTS.adminUserById(userId), body)
}

/** DELETE /api/admin/users/{user_id} */
export function deleteUser(userId: number): Promise<null> {
  return http.delete<null>(ENDPOINTS.adminUserById(userId))
}

/**
 * POST /api/admin/users/{user_id}/reset-password
 * 重置任意用户密码 —— 对管理员账号返回 40904（只能重置普通用户）
 */
export function resetUserPassword(userId: number, body: AdminResetPasswordIn): Promise<null> {
  return http.post<null>(ENDPOINTS.adminUserResetPassword(userId), body)
}
