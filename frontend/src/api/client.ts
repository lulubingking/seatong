/**
 * 统一 HTTP 客户端
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §10.4.1～§10.4.3
 *
 * 【铁律】全部接口调用必须经过本实例。
 * 禁止在业务代码中直接 `fetch` 或新建 Axios 实例（D9 §10.7 自检项）。
 *
 * 拦截器职责边界（D9 §10.4.3「禁止在拦截器里做业务跳转」）：
 *   · 拦截器只负责归一化与呈现，**不做**跳转登录页等路由层动作
 *   · 否则会造成登录页反复弹出的死循环
 * ────────────────────────────────────────────────────────────────
 */

import axios, {
  AxiosError,
  AxiosHeaders,
  type AxiosInstance,
  type AxiosRequestConfig,
} from 'axios'
import type { ApiEnvelope } from './types'
import {
  HEADER_GUEST_SESSION,
  HEADER_REQUEST_ID,
  LS_GUEST_SESSION,
  TIMEOUT_DEFAULT,
} from '@/constants/limits'
import { getErrorSpec, LOCAL_ERROR_CODES } from '@/constants/errorMessages'

/* ── 跨模块轻量状态注入点 ──────────────────────────────────────
   为避免 api/ ↔ stores/ 循环依赖，client 不直接 import authStore，
   而是暴露两个可注入的 getter，由 App 启动时装配。 */

interface ClientHooks {
  /** 取当前 access token，无则返回 null */
  getToken: () => string | null
  /**
   * 令牌失效回调（40101 / 40102）。
   * 只做「清 token + 置游客态」，**不得**在此跳转路由。
   */
  onUnauthorized: (code: string) => void
}

let hooks: ClientHooks = {
  getToken: () => null,
  onUnauthorized: () => {},
}

export function configureClient(next: Partial<ClientHooks>): void {
  hooks = { ...hooks, ...next }
}

/* ── 游客会话 ID ──────────────────────────────────────────────── */

function ensureGuestSessionId(): string {
  let sid: string | null = null
  try {
    sid = window.localStorage.getItem(LS_GUEST_SESSION)
  } catch {
    /* 隐私模式下 localStorage 可能抛错，降级为内存态 */
  }
  if (!sid) {
    sid =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `g-${Date.now()}-${Math.random().toString(16).slice(2)}`
    try {
      window.localStorage.setItem(LS_GUEST_SESSION, sid)
    } catch {
      /* 忽略 */
    }
  }
  return sid
}

/** 读取（必要时创建）游客会话 ID。store 与 client 共用同一实现 */
export function getGuestSessionId(): string {
  return ensureGuestSessionId()
}

/* ── Axios 实例 ──────────────────────────────────────────────── */

export const client: AxiosInstance = axios.create({
  // 开发环境由 Vite 代理转发（vite.config.ts 的 /api → 127.0.0.1:8000）
  baseURL: import.meta.env.VITE_API_BASE ?? '',
  timeout: TIMEOUT_DEFAULT,
  // JWT 走 Header，不使用 Cookie 会话
  withCredentials: false,
})

/* ── 请求拦截器（D9 §10.4.2）────────────────────────────────── */

client.interceptors.request.use((config) => {
  // 统一确保 headers 为 AxiosHeaders 实例（可安全使用 set/get）
  const h = (config.headers = AxiosHeaders.from(config.headers))

  const token = hooks.getToken()
  if (token) {
    h.set('Authorization', `Bearer ${token}`)
  } else {
    // 未登录（游客）→ 附加游客会话标识，供服务端计额度
    h.set(HEADER_GUEST_SESSION, ensureGuestSessionId())
  }

  // 追踪 ID：便于与后端日志对账（后端会回写同名响应头）
  if (!h.get(HEADER_REQUEST_ID)) {
    h.set(
      HEADER_REQUEST_ID,
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
        : `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`,
    )
  }

  return config
})

/* ── 响应拦截器（D9 §10.4.3，六步流程）──────────────────────── */

function makeApiError(
  code: string,
  httpStatus: number | null,
  vars: Record<string, string | number>,
  requestId: string | null,
): ApiErrorLike {
  const spec = getErrorSpec(code)
  let message = spec.message
  for (const [k, v] of Object.entries(vars)) {
    message = message.replaceAll(`{${k}}`, String(v))
  }
  const err = new Error(message) as ApiErrorLike
  err.name = 'ApiError'
  err.code = code
  err.httpStatus = httpStatus
  err.level = spec.level
  err.retryable = spec.retryable
  err.requestId = requestId
  return err
}

export interface ApiErrorLike extends Error {
  code: string
  httpStatus: number | null
  level: 'field' | 'block' | 'global'
  retryable: boolean
  requestId: string | null
}

client.interceptors.response.use(
  (resp) => {
    const body = resp.data as ApiEnvelope<unknown> | undefined

    // 非 JSON 信封（如 CSV 导出）直接放行
    if (!body || typeof body !== 'object' || !('code' in body)) {
      return resp
    }

    const rid = (resp.headers?.[HEADER_REQUEST_ID.toLowerCase()] as string) ?? body.request_id ?? null
    // ② 业务码非 0 → 归一化为 ApiError
    if (body.code !== 0) {
      const err = makeApiError(String(body.code), resp.status, {}, rid)

      // ⑤ 特定码触发附加动作（仅状态处理，不做跳转）
      if (err.code === '40101' || err.code === '40102') {
        hooks.onUnauthorized(err.code)
      }

      return Promise.reject(err)
    }

    return resp
  },
  (error: AxiosError) => {
    // ① 网络层失败（无响应）→ NET-01
    if (!error.response) {
      const isTimeout = error.code === 'ECONNABORTED'
      const err = makeApiError(LOCAL_ERROR_CODES.NETWORK, null, {}, null)
      if (isTimeout) {
        // 超时归入网络类但保留原始语义，便于区分「慢」与「断」
        err.message = '请求超时，请检查网络后重试'
      }
      return Promise.reject(err)
    }

    const status = error.response.status
    const body = error.response.data as ApiEnvelope<unknown> | undefined

    // 有业务码 → 优先按业务码分派（纪律 1：错误码优先，HTTP 状态次之）
    if (body && typeof body === 'object' && 'code' in body && body.code !== 0) {
      const err = makeApiError(String(body.code), status, {}, body.request_id ?? null)
      if (err.code === '40101' || err.code === '40102') {
        hooks.onUnauthorized(err.code)
      }
      return Promise.reject(err)
    }

    // 无业务码（如 500 前的框架级错误）→ 按 HTTP 状态粗粒度归类
    const code = status === 404 ? '40401' : status === 403 ? '40301' : '50001'
    return Promise.reject(makeApiError(code, status, {}, null))
  },
)

/* ── 解包辅助 ────────────────────────────────────────────────── */

/**
 * 发起请求并直接返回 `data` 字段。
 * 业务失败会抛出 {@link ApiErrorLike}，由调用方按 `level` 分派呈现。
 */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const resp = await client.request<ApiEnvelope<T>>(config)
  return resp.data.data
}

/** 返回值含完整信封（需要 `message` 或 `request_id` 时使用） */
export async function requestFull<T>(config: AxiosRequestConfig): Promise<ApiEnvelope<T>> {
  const resp = await client.request<ApiEnvelope<T>>(config)
  return resp.data
}

export const http = {
  get: <T>(url: string, config?: AxiosRequestConfig) =>
    request<T>({ ...config, method: 'GET', url }),
  post: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    request<T>({ ...config, method: 'POST', url, data }),
  put: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    request<T>({ ...config, method: 'PUT', url, data }),
  patch: <T>(url: string, data?: unknown, config?: AxiosRequestConfig) =>
    request<T>({ ...config, method: 'PATCH', url, data }),
  delete: <T>(url: string, config?: AxiosRequestConfig) =>
    request<T>({ ...config, method: 'DELETE', url }),

  /**
   * 原始实例访问 —— 仅用于**非 JSON 信封**的端点（如 CSV 导出，
   * 返回 blob 且无 `code` 字段）。业务端点一律使用上面的封装，
   * 以保证错误归一化生效。
   */
  raw: client,
}

/** 构造带 baseURL 的完整路径（用于附件下载等场景） */
export function absoluteUrl(path: string): string {
  const base = (client.defaults.baseURL ?? '').replace(/\/$/, '')
  return `${base}${path.startsWith('/') ? '' : '/'}${path}`
}

/** 判断是否为归一化后的业务错误 */
export function isApiError(e: unknown): e is ApiErrorLike {
  return e instanceof Error && (e as ApiErrorLike).name === 'ApiError'
}
