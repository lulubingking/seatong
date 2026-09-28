/**
 * 路由表
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §2.2（路由表，13 页）、§10.3.1（三层结构）、§10.3.3（代码分割）
 *
 * 【顺序关键】`/history/compare` 必须排在 `/history/:id` **之前**。
 * 否则 `compare` 会被当作 `id` 参数匹配，导致对比视图永不生效。
 *
 * 【代码分割优先级（§10.3.3）】
 *   立即加载  首页、识别工作台（首屏）
 *   懒加载高  登录、注册、历史记录、历史详情
 *   懒加载中  关于、个人中心、对比视图
 *   懒加载低  用户管理、记录管理、系统配置（仅管理员）
 *   Suspense fallback 使用 **L1 区块级骨架屏**，不使用转圈。
 * ────────────────────────────────────────────────────────────────
 */

import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom'
import AppLayout from '@/layouts/AppLayout'
import AuthLayout from '@/layouts/AuthLayout'
import { RouteGuard } from './guards'
import { PATHS } from './paths'
import PageSkeleton from '@/components/feedback/PageSkeleton'
import ToastHost from '@/components/feedback/ToastHost'
import LoginPrompt from '@/components/feedback/LoginPrompt'

/**
 * 路由根节点 —— 全局浮层的**唯一正确挂载点**。
 *
 * 【为什么必须有这一层（踩坑记录）】
 * `LoginPrompt` 与部分通知逻辑要读 `useNavigate()` / `useLocation()`。
 * 若把它们放在 `<RouterProvider>` **外侧**（曾如此），React Router 会抛
 * 「useNavigate() may be used only in the context of a <Router> component」，
 * 而它又是无错误边界的顶层兄弟节点 → **整棵应用树卸载，页面全白**。
 * 放进路由树的根 layout 后，浮层天然获得 router context，
 * 且 `RouterProvider` 自身的错误处理能兜住子树的渲染异常。
 */
function RootLayout() {
  return (
    <>
      <Outlet />
      <ToastHost />
      <LoginPrompt />
    </>
  )
}

/* ── 立即加载（首屏）─────────────────────────────────────────── */
import Home from '@/pages/Home'
import Recognize from '@/pages/Recognize'

/* ── 懒加载 ──────────────────────────────────────────────────── */
const About = lazy(() => import('@/pages/About'))
const Login = lazy(() => import('@/pages/Login'))
const Register = lazy(() => import('@/pages/Register'))
const HistoryList = lazy(() => import('@/pages/History/List'))
const HistoryDetail = lazy(() => import('@/pages/History/Detail'))
const Compare = lazy(() => import('@/pages/History/Compare'))
const Profile = lazy(() => import('@/pages/Profile'))
const AdminUsers = lazy(() => import('@/pages/Admin/Users'))
const AdminRecords = lazy(() => import('@/pages/Admin/Records'))
const AdminConfig = lazy(() => import('@/pages/Admin/Config'))
const NotFound = lazy(() => import('@/pages/NotFound'))

/** 统一包裹懒加载视图的 Suspense，fallback 为区块级骨架屏 */
function S({ children }: { children: ReactNode }) {
  return <Suspense fallback={<PageSkeleton />}>{children}</Suspense>
}

/** 角色不符时渲染 404（不暴露管理入口存在性，D9 §10.3.2） */
const ForbiddenAs404 = (
  <S>
    <NotFound />
  </S>
)

export const router = createBrowserRouter([
  /* ── 路由根：承载全局浮层（见 RootLayout 注释）────────────── */
  {
    element: <RootLayout />,
    children: [
  {
    path: '/',
    element: <AppLayout />,
    children: [
      /* 1 首页 —— 公开 */
      { index: true, element: <Home /> },

      /* 2 识别工作台 —— 公开（游客限 3 次，额度门禁在提交时） */
      { path: 'recognize', element: <Recognize /> },

      /* 3 关于与免责 —— 公开 */
      {
        path: 'about',
        element: (
          <S>
            <About />
          </S>
        ),
      },

      /* 6 历史记录 —— 需登录 */
      {
        path: 'history',
        element: (
          <RouteGuard requiresAuth>
            <S>
              <HistoryList />
            </S>
          </RouteGuard>
        ),
      },

      /* 8 对比视图 —— 静态段须在动态段之前！ */
      {
        path: 'history/compare',
        element: (
          <RouteGuard requiresAuth>
            <S>
              <Compare />
            </S>
          </RouteGuard>
        ),
      },

      /* 7 历史详情 —— 需登录 */
      {
        path: 'history/:id',
        element: (
          <RouteGuard requiresAuth>
            <S>
              <HistoryDetail />
            </S>
          </RouteGuard>
        ),
      },

      /* 9 个人中心 —— 需登录 */
      {
        path: 'profile',
        element: (
          <RouteGuard requiresAuth>
            <S>
              <Profile />
            </S>
          </RouteGuard>
        ),
      },

      /* 10～12 管理端 —— 需管理员角色；不符则渲染 404 */
      {
        path: 'admin',
        element: <RouteGuard requiresAdmin forbiddenFallback={ForbiddenAs404}><Navigate to={PATHS.adminUsers} replace /></RouteGuard>,
      },
      {
        path: 'admin/users',
        element: (
          <RouteGuard requiresAdmin forbiddenFallback={ForbiddenAs404}>
            <S>
              <AdminUsers />
            </S>
          </RouteGuard>
        ),
      },
      {
        path: 'admin/records',
        element: (
          <RouteGuard requiresAdmin forbiddenFallback={ForbiddenAs404}>
            <S>
              <AdminRecords />
            </S>
          </RouteGuard>
        ),
      },
      {
        path: 'admin/config',
        element: (
          <RouteGuard requiresAdmin forbiddenFallback={ForbiddenAs404}>
            <S>
              <AdminConfig />
            </S>
          </RouteGuard>
        ),
      },

      /* 13 404 兜底（框架内） */
      {
        path: '*',
        element: (
          <S>
            <NotFound />
          </S>
        ),
      },
    ],
  },

  /* ── 无框架路由（居中卡片）────────────────────────────────── */
  {
    element: <AuthLayout />,
    children: [
      /* 4 登录 —— 已登录时重定向首页 */
      {
        path: 'login',
        element: (
          <RouteGuard guestOnly>
            <S>
              <Login />
            </S>
          </RouteGuard>
        ),
      },
      /* 5 注册 */
      {
        path: 'register',
        element: (
          <RouteGuard guestOnly>
            <S>
              <Register />
            </S>
          </RouteGuard>
        ),
      },
    ],
  },
    ],
  },
])

export { PATHS }
