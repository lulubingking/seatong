/**
 * 错误码 → 用户文案映射表
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §7.3（28 条映射）
 * 放置纪律（D9 §10.1.1 第 2 条）：所有面向用户的错误文案只在本文件出现一次，
 * 页面组件**不得**内联错误字符串。
 *
 * 错误码权威来源：PRD §8.3.2（18 个业务码）
 *                + D8 补充 3 个（40902 / 40903 / 40904）
 *                + D9 补充 10 个（42203 / 40402 / 40403 / 50002 / NET-01 / CLI-01 / CLI-02
 *                  以及 §7.3 中作为示例的 2 个）
 * ────────────────────────────────────────────────────────────────
 */

/** 呈现层级：决定错误出现在界面的哪一层（D9 §6.6） */
export type ErrorLevel =
  | 'field'   // 字段级 —— 字段下方红字 + 红边，聚焦首个非法字段
  | 'block'   // 区块级 —— 该区块内 Alert + 重试，其余区域正常
  | 'global'  // 全局级 —— Toast / 顶部 Alert，影响整个页面或整个应用

export interface ErrorSpec {
  /** 业务错误码（字符串，与后端响应体 code 字段比较时须先转字符串） */
  code: string
  /** 呈现层级 */
  level: ErrorLevel
  /**
   * 用户可见文案。
   * 含 `{n}` / `{days}` / `{max}` 占位符时，须由调用方运行时替换，
   * 不得写死具体数值（D9 §7.3.6 纪律 5）。
   */
  message: string
  /** 是否提供重试按钮。为 false 时**禁止**渲染重试入口（D9 §7.3.6 纪律 4） */
  retryable: boolean
  /** 前端附加行为说明（仅供开发者参考，不呈现给用户） */
  action?: string
  /** 文案是否含占位符，需运行时替换 */
  templated?: boolean
}

/**
 * 28 条映射。按 §7.3 的 5 个小节顺序排列，便于与文档对照。
 */
export const ERROR_SPECS: Record<string, ErrorSpec> = {
  /* ── §7.3.1 参数与校验类（400xx / 413xx / 415xx / 422xx）────────── */

  '40001': {
    code: '40001',
    level: 'field',
    message: '请检查填写内容后重试',
    retryable: false,
    action: '聚焦首个非法字段',
  },
  '41301': {
    code: '41301',
    level: 'field',
    message: '图片体积不能超过 {max}MB，请压缩后重试',
    retryable: false,
    action: '角标报错，不进入上传队列',
    templated: true,
  },
  '41501': {
    code: '41501',
    level: 'field',
    message: '仅支持 JPG、PNG、BMP 格式的图片',
    retryable: false,
    action: '角标报错，不进入上传队列',
  },
  '42201': {
    code: '42201',
    level: 'block',
    message: '这张图片无法读取，可能已损坏，请更换后重试',
    retryable: true,
    action: '文件卡片标记失败',
  },
  '42202': {
    code: '42202',
    level: 'field',
    message: '图片尺寸过小，请上传清晰度更高的图片',
    retryable: false,
    action: '角标报错',
  },
  '42203': {
    code: '42203',
    level: 'field',
    // 具体文案按使用字段而定，见 D9 §5.4 / §5.5 / §5.12
    message: '填写内容不符合要求，请修改后重试',
    retryable: false,
    action: '字段下方红字 + 红边；具体文案由调用处按字段覆写',
  },

  /* ── §7.3.2 认证与账号类（401xx）─────────────────────────────── */

  '40101': {
    code: '40101',
    level: 'global',
    message: '请先登录后再操作',
    retryable: false,
    action: '打开登录引导弹窗，保留上下文',
  },
  '40102': {
    code: '40102',
    level: 'global',
    message: '登录状态已过期，请重新登录',
    retryable: false,
    action: '清 token，降级游客态，Toast 轻提示（不跳转）',
  },
  '40103': {
    code: '40103',
    level: 'field',
    message: '账号或密码错误，请重新输入',
    retryable: false,
    action: '表单顶部 Alert；清空密码、保留账号',
  },
  '40104': {
    code: '40104',
    level: 'global',
    message: '这个账号已被禁用，请联系管理员',
    retryable: false,
    action: '停留登录页，不写入 token',
  },
  '40105': {
    code: '40105',
    level: 'global',
    message: '账号已锁定，请 {n} 分钟后重试',
    retryable: true,
    action: '展示剩余时间，登录按钮倒计时禁用',
    templated: true,
  },

  /* ── §7.3.3 权限与限流类（403xx / 429xx）─────────────────────── */

  '40301': {
    code: '40301',
    level: 'global',
    message: '你没有执行此操作的权限',
    retryable: false,
    action: '就地提示，不跳转（防权限探测）',
  },
  '42901': {
    code: '42901',
    level: 'global',
    message: '试用次数已用完，登录后可继续使用',
    retryable: false,
    action: '打开登录引导 + 注册入口',
  },
  '42902': {
    code: '42902',
    level: 'global',
    message: '操作过于频繁，请 {n} 秒后重试',
    retryable: true,
    action: 'Toast 警示 + 按钮倒计时禁用',
    templated: true,
  },

  /* ── §7.3.4 资源与状态类（404xx / 409xx）─────────────────────── */

  '40401': {
    code: '40401',
    level: 'block',
    // 对「他人资源」与「不存在资源」统一返回此码（D9 §6.6，防 ID 枚举）
    message: '这条记录不存在或已被删除',
    retryable: false,
    action: '详情页转 404 兜底视图',
  },
  '40402': {
    code: '40402',
    level: 'block',
    message: '原图已不可用，可能已超过留存期',
    retryable: false,
    action: '图片区用占位块，其余内容正常渲染',
  },
  '40403': {
    code: '40403',
    level: 'block',
    message: '这个账号不存在或已被删除',
    retryable: false,
    action: '列表行就地报错',
  },
  '40901': {
    code: '40901',
    level: 'field',
    message: '该账号名已被使用，请更换',
    retryable: false,
    action: '账号字段红字，保留其他字段值',
  },
  '40902': {
    code: '40902',
    level: 'block',
    message: '不能禁用当前登录的账号',
    retryable: false,
    action: '开关回弹',
  },
  '40903': {
    code: '40903',
    level: 'block',
    message: '系统须保留至少一个可用的管理员账号',
    retryable: false,
    action: '开关回弹 + 就地说明',
  },
  '40904': {
    code: '40904',
    level: 'block',
    message: '只能重置普通用户的密码',
    retryable: false,
    action: '按钮置灰 + title 说明',
  },

  /* ── §7.3.5 服务端与网络类（500xx / 503xx / 前端补充）──────────── */

  '50001': {
    code: '50001',
    level: 'block',
    message: '服务出现异常，请稍后重试',
    retryable: true,
    action: 'Alert 持久展示 + 重试按钮；记录 request_id 便于对账',
  },
  '50002': {
    code: '50002',
    level: 'block',
    message: '识别失败，请确认图片清晰、主体完整后重试',
    retryable: true,
    action: '★ 保留 image_id，仅重跑推理，**不重复扣减额度**',
  },
  '50301': {
    code: '50301',
    level: 'block',
    message: '识别服务正在维护，请稍后再试',
    retryable: true,
    action: '禁用「开始识别」按钮 + 顶栏状态提示',
  },
  '50302': {
    code: '50302',
    level: 'block',
    message: '当前请求较多，请稍后重试',
    retryable: true,
    action: '可自动重试一次（指数退避）',
  },

  /* ── 前端补充码（非后端返回，由客户端本地产生）────────────────── */

  'NET-01': {
    code: 'NET-01',
    level: 'global',
    message: '网络连接异常，请检查网络后重试',
    retryable: true,
    action: 'Toast 展示 5 s；上传作业进入 UPLOAD_FAILED 态',
  },
  'CLI-01': {
    code: 'CLI-01',
    level: 'field',
    message: '仅支持 JPG、PNG、BMP 格式，单张不超过 {max}MB，单次最多 {count} 张',
    retryable: false,
    action: '选择文件时立即拦截，不发出请求',
    templated: true,
  },
  'CLI-02': {
    code: 'CLI-02',
    level: 'field',
    message: '剪贴板中没有可用的图片',
    retryable: false,
    action: '不改变当前状态',
  },
}

/** 未知错误码的兜底规格（D9 §7.3.6 纪律 2） */
export const FALLBACK_SPEC: ErrorSpec = ERROR_SPECS['50001']

/** 前端本地错误码常量 */
export const LOCAL_ERROR_CODES = {
  NETWORK: 'NET-01',
  FILE_VALIDATE: 'CLI-01',
  CLIPBOARD_EMPTY: 'CLI-02',
} as const

/**
 * 按错误码取规格。未知码一律回落到 50001 的文案与层级，
 * 同时 console.warn 记录（**不得透传后端原始 message**）。
 */
export function getErrorSpec(code: string | number | null | undefined): ErrorSpec {
  const key = code == null ? '' : String(code)
  const spec = ERROR_SPECS[key]
  if (spec) return spec

  if (key !== '') {
    // eslint-disable-next-line no-console
    console.warn(`[errorMessages] 未知错误码 ${key}，按 50001 处理`)
  }
  return FALLBACK_SPEC
}

/**
 * 替换文案中的占位符。
 * 未提供对应变量时保留原占位符（便于在联调期发现遗漏），不做静默兜底。
 */
export function formatError(
  code: string | number | null | undefined,
  vars: Record<string, string | number> = {},
): { message: string; level: ErrorLevel; retryable: boolean; code: string } {
  const spec = getErrorSpec(code)
  let message = spec.message
  for (const [k, v] of Object.entries(vars)) {
    message = message.replaceAll(`{${k}}`, String(v))
  }
  return { message, level: spec.level, retryable: spec.retryable, code: spec.code }
}

/**
 * 使用纪律（D9 §7.3.6，五条，实现时须遵守）：
 *
 * 1. **错误码优先，HTTP 状态次之**。
 *    同 HTTP 状态可能对应多个业务码（401 下有 5 个、403 下 1 个、
 *    429 下 2 个、503 下 2 个），必须按响应体的 code 分派，不得按状态码分派。
 *
 * 2. **未知错误码回落到 50001**，console.warn 记录，
 *    **不得**把后端原始 message 透传给用户（可能含技术细节或英文堆栈）。
 *
 * 3. **额度扣减联动**：仅 `50002` 明确不扣额度（失败重试免费）；
 *    其余错误后须**主动重新拉取**当前剩余额度，避免本地状态与后端不一致。
 *
 * 4. **可重试列是强约束**：标 `retryable: false` 的错误**不得**渲染重试按钮 ——
 *    重试注定失败（如格式错误、体积超限、权限不足），提供入口只会消耗用户耐心。
 *
 * 5. **文案变量占位**：`{n}`（秒数 / 分钟数）、`{days}`（留存期天数）、
 *    `{max}`（体积上限）、`{count}`（单批上限）须运行时替换，不得写死数值。
 */
