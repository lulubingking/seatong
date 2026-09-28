import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// 前端 5180 / 后端 8000（PRD 8.5 联调约定）
// 【为什么是 5180 而不是 Vite 默认的 5173】
// 5173 已被同机并行的另一项目（批小智 AI 作业批改工作台）长期占用，
// 且本配置启用了 strictPort —— 若仍写 5173，dev server 会直接启动失败
// 或被手动 --port 覆盖，造成「配置 / 文档 / 自检脚本」三处口径不一致。
// 自检脚本 frontend/scripts/route-smoke.mjs 的默认基址同为 5180。
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: '127.0.0.1',
    port: 5180,
    strictPort: true,
    // 开发期通过代理访问后端，避免跨域与环境变量分歧。
    // 生产部署时应改为同源反向代理（见部署运维手册）。
    proxy: {
      '/api': {
        target: process.env.SEATONG_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
})
