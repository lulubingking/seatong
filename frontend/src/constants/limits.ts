/**
 * 客户端限额与阈值常量
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：
 *   · PRD §8.1 / 14 项决策基线（单图 ≤10 MB、批量 ≤9 张）
 *   · D9 §5.2（识别工作台）、§5.6（历史列表）、§5.10～§5.12（管理页）
 *   · 后端 settings（前缀 SEATONG_）—— 若后端调整，本文件须同步
 *
 * 纪律：所有魔法数字只在本文件出现一次，组件不得内联数值。
 * ────────────────────────────────────────────────────────────────
 */

/** 文件体积上限（字节）。PRD 决策基线：单图 ≤10 MB */
export const MAX_FILE_BYTES = 10 * 1024 * 1024

/** 文件体积上限（MB，用于文案占位符替换） */
export const MAX_FILE_MB = 10

/** 单批上传张数上限。PRD 决策基线：批量 ≤9 张 */
export const MAX_BATCH_FILES = 9

/** 允许的图片 MIME 类型（PRD + D9 §7.3 `CLI-01`） */
export const ACCEPTED_MIME_TYPES = [
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/bmp',
  'image/x-ms-bmp',
] as const

/** 允许的扩展名（用于 `accept` 属性与双重校验） */
export const ACCEPTED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.bmp'] as const

/** `accept` 属性值 */
export const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(',')

/** 图片最小边长（px）。低于此值返回 42202 */
export const MIN_IMAGE_SIDE = 32

/** 上传并发池大小（D9 §6.4：并发数 = 3） */
export const UPLOAD_CONCURRENCY = 3

/** 游客免登录试用次数（PRD 决策基线） */
export const GUEST_QUOTA = 3

/** Top-K 候选数（PRD：结果展示 Top-5） */
export const TOP_K = 5

/** 对比视图可选记录条数区间（D9 §5.8） */
export const COMPARE_MIN = 2
export const COMPARE_MAX = 4

/** 分页大小 */
export const PAGE_SIZE_DEFAULT = 20
export const PAGE_SIZE_OPTIONS = [10, 20, 50] as const

/** 管理端用户列表分页大小（D9 §5.10） */
export const ADMIN_PAGE_SIZE = 20

/** 密码最小长度（D9 §5.5 注册页校验） */
export const PASSWORD_MIN_LENGTH = 8

/** 账号名长度区间（D9 §5.5） */
export const USERNAME_MIN_LENGTH = 3
export const USERNAME_MAX_LENGTH = 32

/** 昵称长度上限 */
export const NICKNAME_MAX_LENGTH = 32

/** 关键词搜索长度上限（D9 §5.6） */
export const KEYWORD_MAX_LENGTH = 50

// ── 超时（D9 §10.4.1）──────────────────────────────────────────

/** 常规请求超时：列表、详情、配置类 */
export const TIMEOUT_DEFAULT = 15_000

/** 单文件上传超时 */
export const TIMEOUT_UPLOAD = 60_000

/** 识别请求超时（含首次模型加载） */
export const TIMEOUT_RECOGNIZE = 60_000

// ── 动效时长（D9 §3.9，单位 ms）─────────────────────────────────

/** 微交互时长区间 [下限, 上限] */
export const MOTION_MIN = 150
export const MOTION_MAX = 300
/** Top-5 条形图填充动画（显式例外） */
export const MOTION_BAR = 450

// ── 响应式断点（D9 §8.1，单位 px）──────────────────────────────

/** XS 上限：< 768 */
export const BP_SM = 768
/** MD 上限：768 ～ 1023 */
export const BP_MD = 1024
/** LG 上限：1024 ～ 1439 */
export const BP_LG = 1440

// ── 请求头名称 ──────────────────────────────────────────────────

/** 游客会话标识头（后端约定） */
export const HEADER_GUEST_SESSION = 'X-Guest-Session'
/** 请求追踪 ID 头（后端回写，与响应信封 `request_id` 一致） */
export const HEADER_REQUEST_ID = 'X-Request-Id'

/** localStorage 键名（仅存游客会话 ID，不存物种字典 —— D9 §10.5） */
export const LS_GUEST_SESSION = 'seatong.guest_session'
