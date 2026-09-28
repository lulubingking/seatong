/**
 * 图片资源接口 —— `/api/images*`（4 个端点，D8 §6）
 *
 * 【关键语义】上传与识别**分离**：
 *   `POST /api/images` 只落盘、不推理，**不消耗游客额度**。
 *   额度在 `/api/recognize` 成功返回后扣减（D7 §2.2 / PRD BR-UPLOAD-*）。
 */

import { http, client, getGuestSessionId } from './client'
import { getTokenSync } from '@/stores/authStore'
import { ENDPOINTS } from './index'
import { TIMEOUT_UPLOAD } from '@/constants/limits'
import type { UploadOut } from './types'

/**
 * POST /api/images —— 单张上传（multipart/form-data）
 *
 * @param file      待上传文件
 * @param onProgress 上传进度回调（0–100）
 */
export function uploadImage(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<UploadOut> {
  const form = new FormData()
  form.append('file', file, file.name)
  return http.post<UploadOut>(ENDPOINTS.images, form, {
    timeout: TIMEOUT_UPLOAD,
    onUploadProgress: (e) => {
      if (!onProgress || !e.total) return
      onProgress(Math.round((e.loaded / e.total) * 100))
    },
  })
}

/**
 * `<img>` 标签的请求无法携带 `Authorization` / `X-Guest-Session` 请求头，
 * 后端对图像端点提供查询参数兜底：登录用户拼 `access_token`，
 * 游客拼 `guest_session`（与请求头同名的降级通道，D8 §6.4/§6.5）。
 */
function credentialQuery(): string {
  const token = getTokenSync()
  if (token) return `access_token=${encodeURIComponent(token)}`
  return `guest_session=${encodeURIComponent(getGuestSessionId())}`
}

function withCredential(url: string): string {
  return `${url}${url.includes('?') ? '&' : '?'}${credentialQuery()}`
}

/**
 * 构造图片内容的完整 URL。
 * 后端返回的是**相对路径**（如 `/api/images/{id}/content`），
 * 因存在 `/api` 前缀与独立端口，须拼 baseURL 才能被 `<img src>` 直接使用。
 */
export function imageContentUrl(imageId: string): string {
  const base = (client.defaults.baseURL ?? '').replace(/\/$/, '')
  return withCredential(`${base}${ENDPOINTS.imageContent(imageId)}`)
}

/** 构造缩略图 URL（列表项用，体积更小）。`thumb_url` 已是相对路径时可直接用此函数 */
export function imageThumbUrl(imageId: string): string {
  const base = (client.defaults.baseURL ?? '').replace(/\/$/, '')
  return withCredential(`${base}${ENDPOINTS.imageThumb(imageId)}`)
}

/** 把后端返回的相对路径（`thumb_url` 等）补全为可用 URL */
export function resolveAssetUrl(relative: string | null | undefined): string | null {
  if (!relative) return null
  if (/^https?:\/\//i.test(relative)) return relative
  const base = (client.defaults.baseURL ?? '').replace(/\/$/, '')
  const full = `${base}${relative.startsWith('/') ? '' : '/'}${relative}`
  return withCredential(full)
}

/**
 * DELETE /api/images/{image_id} —— 删除尚未识别的图片（清理用，D8 §6.5）
 *
 * **仅对已登录用户开放**：游客上传的图无归属信息，服务端无法判定归属，
 * 因此游客调用会得到 40101。若图片已产生识别记录，返回 42201
 * —— 请改用 {@link deleteOneRecord} 走历史记录的软删除，避免级联丢失历史。
 */
export function deleteImage(imageId: string): Promise<null> {
  return http.delete<null>(ENDPOINTS.imageById(imageId))
}
