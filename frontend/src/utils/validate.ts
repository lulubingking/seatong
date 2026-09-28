/**
 * 客户端校验
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §7.3 `CLI-01`（选择文件时立即拦截，不发请求）
 *           + §5.4 / §5.5 表单校验
 *
 * 【原则】客户端校验只为**减少无效请求**与**即时反馈**，
 * 最终以服务端校验为准。服务端返回的字段级错误须覆盖本地判定。
 * ────────────────────────────────────────────────────────────────
 */

import {
  ACCEPTED_EXTENSIONS,
  ACCEPTED_MIME_TYPES,
  MAX_FILE_BYTES,
  MAX_FILE_MB,
  MAX_BATCH_FILES,
  MIN_IMAGE_SIDE,
  PASSWORD_MIN_LENGTH,
  USERNAME_MAX_LENGTH,
  USERNAME_MIN_LENGTH,
} from '@/constants/limits'
import { LOCAL_ERROR_CODES } from '@/constants/errorMessages'

export interface FileReject {
  file: File
  /** 前端本地错误码（CLI-01 等） */
  code: string
  /** 已替换占位符的最终文案 */
  message: string
}

export interface FileValidationResult {
  accepted: File[]
  rejected: FileReject[]
  /** 超量被截断的文件（须提示用户，不静默丢弃） */
  overflow: File[]
}

const EXT_RE = new RegExp(
  `(${ACCEPTED_EXTENSIONS.map((e) => e.replace('.', '\\.')).join('|')})$`,
  'i',
)

function reject(file: File, message: string): FileReject {
  return { file, code: LOCAL_ERROR_CODES.FILE_VALIDATE, message }
}

/** 单文件校验：MIME 与扩展名双重判定（MIME 可能为空或伪造） */
export function validateFile(file: File): FileReject | null {
  const byMime = (ACCEPTED_MIME_TYPES as readonly string[]).includes(file.type)
  const byExt = EXT_RE.test(file.name)

  if (!byMime && !byExt) {
    return reject(
      file,
      '仅支持 JPG、PNG、BMP 格式，单张不超过 10MB，单次最多 9 张',
    )
  }
  if (file.size > MAX_FILE_BYTES) {
    return reject(file, `图片体积不能超过 ${MAX_FILE_MB}MB，请压缩后重试`)
  }
  if (file.size === 0) {
    return reject(file, '这张图片无法读取，可能已损坏，请更换后重试')
  }
  return null
}

/**
 * 批量校验。返回可入队文件、被拒文件、超量文件。
 *
 * @param existing  已在队列中的文件数（用于计算剩余额度）
 * @param force     用户已确认「继续添加」后传 true —— 此模式下**全部**通过
 *                  单文件校验的文件都入队（连同超量部分），且调用方**不再**
 *                  重复弹出校验失败汇总弹窗（原型曾因此重复弹窗，已修复）
 */
export function validateFiles(
  incoming: File[],
  existing = 0,
  force = false,
): FileValidationResult {
  const accepted: File[] = []
  const rejected: FileReject[] = []

  for (const f of incoming) {
    const r = validateFile(f)
    if (r) rejected.push(r)
    else accepted.push(f)
  }

  if (force) {
    // 用户已确认超限，全部放行（单文件校验不通过者仍在 rejected 中）
    return { accepted, rejected, overflow: [] }
  }

  const room = Math.max(0, MAX_BATCH_FILES - existing)
  return {
    accepted: accepted.slice(0, room),
    rejected,
    overflow: accepted.slice(room),
  }
}

/** 校验图片自然尺寸（选出后异步读取）。低于 {@link MIN_IMAGE_SIDE} 返回错误文案 */
export function validateImageSize(file: File): Promise<string | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      const tooSmall = img.naturalWidth < MIN_IMAGE_SIDE || img.naturalHeight < MIN_IMAGE_SIDE
      URL.revokeObjectURL(url)
      resolve(tooSmall ? '图片尺寸过小，请上传清晰度更高的图片' : null)
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      resolve('这张图片无法读取，可能已损坏，请更换后重试')
    }
    img.src = url
  })
}

/* ── 表单校验 ────────────────────────────────────────────────── */

export interface FieldError {
  field: string
  /** 一句话说明问题所在（禁忌 A-04：不得写「格式错误」这种无信息量表述） */
  message: string
}

/** 账号名：3–32 字符，限字母/数字/下划线 */
export function validateUsername(v: string): FieldError | null {
  const s = v.trim()
  if (!s) return { field: 'username', message: '请输入账号名' }
  if (s.length < USERNAME_MIN_LENGTH)
    return { field: 'username', message: `账号名至少 ${USERNAME_MIN_LENGTH} 个字符` }
  if (s.length > USERNAME_MAX_LENGTH)
    return { field: 'username', message: `账号名最多 ${USERNAME_MAX_LENGTH} 个字符` }
  if (!/^[A-Za-z0-9_]+$/.test(s))
    return { field: 'username', message: '账号名只能包含字母、数字和下划线' }
  return null
}

/** 密码：≥8 位，且须同时含字母与数字 */
export function validatePassword(v: string): FieldError | null {
  if (!v) return { field: 'password', message: '请输入密码' }
  if (v.length < PASSWORD_MIN_LENGTH)
    return { field: 'password', message: `密码至少 ${PASSWORD_MIN_LENGTH} 位` }
  if (!/[A-Za-z]/.test(v) || !/\d/.test(v))
    return { field: 'password', message: '密码须同时包含字母和数字' }
  return null
}

/** 确认密码 */
export function validateConfirm(pwd: string, confirm: string): FieldError | null {
  if (!confirm) return { field: 'confirm', message: '请再次输入密码' }
  if (pwd !== confirm) return { field: 'confirm', message: '两次输入的密码不一致' }
  return null
}

/** 邮箱（可空） */
export function validateEmail(v: string): FieldError | null {
  const s = v.trim()
  if (!s) return null
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s))
    return { field: 'email', message: '邮箱地址格式不正确' }
  if (s.length > 120) return { field: 'email', message: '邮箱地址最多 120 个字符' }
  return null
}

/** 昵称（可空，≤20 —— 后端 `AdminUserUpdateIn.nickname` maxLength=20） */
export function validateNickname(v: string): FieldError | null {
  const s = v.trim()
  if (!s) return null
  if (s.length > 20) return { field: 'nickname', message: '昵称最多 20 个字符' }
  return null
}

/** 密码强度（0–4），驱动密码强度条 */
export function passwordStrength(v: string): number {
  let n = 0
  if (v.length >= 8) n++
  if (v.length >= 12) n++
  if (/[A-Za-z]/.test(v) && /\d/.test(v)) n++
  if (/[^A-Za-z0-9]/.test(v)) n++
  return Math.min(n, 4)
}

/** 首轮校验，返回第一个错误（用于「聚焦首个非法字段」） */
export function firstError(...results: Array<FieldError | null>): FieldError | null {
  return results.find((r): r is FieldError => r !== null) ?? null
}
