/**
 * 路由路径常量（D9 §10.1.1 放置纪律 1）
 *
 * 【硬性纪律】路径字符串只允许出现在本文件。
 * 其余任何位置一律引用此处的常量 —— 路由改名时才能一处生效。
 * 提交前自检项：「无硬编码路由字符串（全部来自 paths.ts）」。
 */
export const PATHS = {
  home: '/',
  recognize: '/recognize',
  about: '/about',
  login: '/login',
  register: '/register',
  history: '/history',
  historyDetail: (id = ':id') => `/history/${id}`,
  /** 静态段须排在动态段之前（D9 §10.3.1），此处顺序即路由注册顺序的依据 */
  historyCompare: '/history/compare',
  profile: '/profile',
  adminUsers: '/admin/users',
  adminRecords: '/admin/records',
  adminConfig: '/admin/config',
} as const

/** 路由名 ↔ 视图键，与高保真原型的 `var VIEWS` 13 键一一对应（D9 §2.2） */
export type RouteKey =
  | 'home'
  | 'recognize'
  | 'about'
  | 'login'
  | 'register'
  | 'history'
  | 'historyDetail'
  | 'compare'
  | 'profile'
  | 'adminUsers'
  | 'adminRecords'
  | 'adminConfig'
  | 'notFound'
