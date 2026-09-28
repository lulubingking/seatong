/**
 * 应用根组件
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §10.3（路由与守卫）、§10.4（API 对接）
 *
 * 职责：
 *   1. 装配 client 拦截器 ↔ authStore 的双向钩子（避免循环依赖）
 *   2. bootstrap 会话（`GET /users/me`），**完成前不挂载路由** ——
 *      防止带 token 的用户在会话确认前被守卫误踢到登录页
 *   3. 挂载 Toast 宿主与登录引导弹窗
 * ────────────────────────────────────────────────────────────────
 */

import { useEffect, useState } from 'react'
import { RouterProvider } from 'react-router-dom'
import { Spin } from 'antd'
import { configureClient } from '@/api/client'
import { onUnauthorizedSync, getTokenSync, useAuthStore } from '@/stores/authStore'
import { useSpeciesStore } from '@/stores/speciesStore'
import { router } from '@/routes'

export default function App() {
  const bootstrap = useAuthStore((s) => s.bootstrap)
  const resolved = useAuthStore((s) => s.resolved)
  const ensureSpecies = useSpeciesStore((s) => s.ensureLoaded)
  const [bootError, setBootError] = useState<string | null>(null)

  useEffect(() => {
    // ① 装配拦截器钩子（client 不 import store，由此处注入，打破循环依赖）
    configureClient({
      getToken: getTokenSync,
      onUnauthorized: onUnauthorizedSync,
    })

    // ② 会话确认
    bootstrap()
      .then(() => ensureSpecies())
      .catch((e: unknown) => {
        setBootError(e instanceof Error ? e.message : '初始化失败')
      })
  }, [bootstrap, ensureSpecies])

  if (bootError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg p-6">
        <div className="max-w-md w-full rounded-lg border border-line bg-surface p-6 text-center">
          <h1 className="text-[17px] font-semibold text-ink m-0 mb-2">页面初始化失败</h1>
          <p className="text-[13.5px] text-ink-2 m-0 mb-4">{bootError}</p>
          <button
            type="button"
            className="min-h-[36px] px-4 rounded-sm text-white text-[13.5px]"
            style={{ background: 'var(--primary)' }}
            onClick={() => window.location.reload()}
          >
            重新加载页面
          </button>
        </div>
      </div>
    )
  }

  if (!resolved) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-bg">
        <Spin size="large" />
        <p className="text-[13.5px] text-ink-2 m-0">正在载入…</p>
      </div>
    )
  }

  return (
    <>
      {/*
       * Toast 宿主与登录引导弹窗**不在此处挂载** ——
       * 它们需要 `useNavigate()` / `useLocation()`，必须位于路由上下文内。
       * 若放在 <RouterProvider> 外侧会抛错并卸载整棵树（页面全白）。
       * 现挂载在路由根 layout（src/routes/index.tsx 的 RootLayout）。
       */}
      <RouterProvider router={router} />
    </>
  )
}
