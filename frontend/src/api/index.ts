/**
 * API 层统一出口
 *
 * 使用方式：
 *   import { authApi, recordsApi } from '@/api'
 *
 * 或按需导入：
 *   import { listHistory } from '@/api/records'
 */

export * as authApi from './auth'
export * as usersApi from './users'
export * as imagesApi from './images'
export * as recognizeApi from './recognize'
export * as recordsApi from './records'
export * as speciesApi from './species'
export * as configApi from './config'

export type * from './types'
export { configureClient, getGuestSessionId, isApiError, absoluteUrl } from './client'
export type { ApiErrorLike } from './client'

/**
 * 端点路径常量（与 D8 V1.1 / 后端 openapi 实测一致，38 条 = 35 主路径 + 3 别名）
 * —— 仅供需要自行拼接 URL 的场景（如附件下载），业务调用请用上面的模块函数。
 *
 * 【命名纪律】本表是前端唯一的路径来源，任何模块不得内联字符串字面量路径。
 */
export const ENDPOINTS = {
  // auth (4)
  register: '/api/auth/register',
  login: '/api/auth/login',
  refresh: '/api/auth/refresh',
  logout: '/api/auth/logout',

  // users 自助 (3)
  me: '/api/users/me',
  myPassword: '/api/users/me/password',

  // guest (1)
  guestQuota: '/api/guest/quota',

  // images (4)
  images: '/api/images',
  imageById: (id: string) => `/api/images/${id}`,
  imageContent: (id: string) => `/api/images/${id}/content`,
  imageThumb: (id: string) => `/api/images/${id}/thumb`,

  // recognize (2) + results (1)
  recognize: '/api/recognize',
  recognizeBatch: '/api/recognize/batch',
  candidates: (recordId: string) => `/api/results/${recordId}/candidates`,

  // records (5) —— 文档权威路径（D8 §7）
  records: '/api/records',
  recordById: (id: string) => `/api/records/${id}`,
  recordsExport: '/api/records/export',

  // history 别名 (3) —— 兼容层，新代码请用 records*
  history: '/api/history',
  historyById: (id: string) => `/api/history/${id}`,
  historyExport: '/api/history/export',

  // admin records (2)
  adminRecords: '/api/admin/records',
  adminRecordById: (id: string) => `/api/admin/records/${id}`,

  // admin users (5) —— 管理端独立命名空间（D8 §9.1～9.3）
  adminUsers: '/api/admin/users',
  adminUserById: (id: number | string) => `/api/admin/users/${id}`,
  adminUserResetPassword: (id: number | string) =>
    `/api/admin/users/${id}/reset-password`,

  // species (2)
  species: '/api/species',
  speciesById: (id: number) => `/api/species/${id}`,

  // admin config / logs / stats (4)
  adminConfig: '/api/admin/config',
  adminLogs: '/api/admin/logs',
  adminStats: '/api/admin/stats',

  // system (2)
  health: '/api/health',
  modelInfo: '/api/model-info',
} as const
