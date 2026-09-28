/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API 基址。开发环境留空走 Vite 代理；生产环境填后端完整地址 */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
