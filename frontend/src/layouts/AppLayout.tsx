/**
 * 应用主框架
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §2.4（全局框架）、§8.2（移动端导航）
 *
 * 结构：粘性顶栏（z-index: 60）+ 内容容器 + 页脚
 * 移动端：顶栏改为汉堡入口 + 抽屉导航
 *
 * 【z-index 纪律】全站仅 4 档：2 局部叠层 / 60 粘性顶栏 / 200 遮罩 / 300 最高浮层。
 * 顶栏用 `z-topbar`（60），遮罩与浮层由 AntD / Toast 组件自行管理。
 * ────────────────────────────────────────────────────────────────
 */

import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Avatar, Dropdown, Button } from 'antd'
import { PATHS } from '@/routes/paths'
import { useAuthStore } from '@/stores/authStore'
import { useUiStore } from '@/stores/uiStore'
import { useSpeciesStore } from '@/stores/speciesStore'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import { useEffect, useState } from 'react'
import * as configApi from '@/api/config'
import MobileDrawer from './MobileDrawer'

/** 主导航 5 项（D9 §2.5） */
const NAV = [
  { to: PATHS.home, label: '首页' },
  { to: PATHS.recognize, label: '识别' },
  { to: PATHS.history, label: '历史记录' },
  { to: PATHS.about, label: '关于' },
] as const

export default function AppLayout() {
  const location = useLocation()
  const { isMobile } = useBreakpoint()
  const openDrawer = useUiStore((s) => s.openDrawer)
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn())
  const isAdmin = useAuthStore((s) => s.isAdmin())
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const guestQuota = useAuthStore((s) => s.guestQuota)
  const ensureSpecies = useSpeciesStore((s) => s.ensureLoaded)

  /** 服务状态（顶栏指示器，D9 §7.1） */
  const [ready, setReady] = useState<boolean | null>(null)

  useEffect(() => {
    // 物种字典懒加载一次（D9 §10.5）
    void ensureSpecies()
    // 服务健康检查（失败静默，仅影响指示器）
    // 注意：ready 在 `model` 嵌套对象里，不是顶层字段
    configApi
      .getHealth()
      .then((h) => setReady(h.model?.ready ?? false))
      .catch(() => setReady(false))
  }, [ensureSpecies])

  // 每次路由变化回到顶部（长列表页切换时必要）
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior })
  }, [location.pathname])

  const menuItems = [
    { key: 'profile', label: <Link to={PATHS.profile}>个人中心</Link> },
    ...(isAdmin
      ? [
          { key: 'admin-users', label: <Link to={PATHS.adminUsers}>用户管理</Link> },
          { key: 'admin-records', label: <Link to={PATHS.adminRecords}>记录管理</Link> },
          { key: 'admin-config', label: <Link to={PATHS.adminConfig}>系统配置</Link> },
        ]
      : []),
    { type: 'divider' as const },
    { key: 'logout', label: '退出登录', danger: true },
  ]

  return (
    <div className="min-h-screen flex flex-col bg-bg text-ink">
      <a href="#main" className="skip-link">
        跳到主要内容
      </a>

      {/* ── 粘性顶栏 ───────────────────────────────────────── */}
      <header
        className="sticky top-0 z-topbar bg-surface border-b border-line"
        role="banner"
      >
        <div className="mx-auto max-w-[1200px] px-4 sm:px-6 h-14 flex items-center gap-4">
          {isMobile && (
            <button
              type="button"
              aria-label="打开导航菜单"
              className="p-2 -ml-2 rounded-sm hover:bg-surface-3 transition-colors"
              onClick={openDrawer}
            >
              <HamburgerIcon />
            </button>
          )}

          <Link
            to={PATHS.home}
            className="flex items-center gap-2 font-semibold text-[15px] text-ink no-underline shrink-0"
          >
            <BrandMark />
            <span>海瞳鱼鉴</span>
          </Link>

          {!isMobile && (
            <nav className="flex items-center gap-1 ml-2" aria-label="主导航">
              {NAV.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  end={n.to === PATHS.home}
                  className={({ isActive }) =>
                    [
                      'px-3 py-1.5 rounded-sm text-[13.5px] no-underline transition-colors',
                      'hover:bg-surface-3',
                      isActive
                        ? 'text-brand font-semibold bg-brand-50'
                        : 'text-ink-2 hover:text-ink',
                    ].join(' ')
                  }
                >
                  {n.label}
                </NavLink>
              ))}
            </nav>
          )}

          <div className="flex-1" />

          {/* 服务状态指示器 */}
          <ServiceBadge ready={ready} />

          {/* 游客额度 */}
          {!isLoggedIn && guestQuota && (
            <span className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-brand-50 text-brand text-[12.5px]">
              试用剩余 <b className="num">{guestQuota.remaining}</b> 次
            </span>
          )}

          {isLoggedIn && user ? (
            <Dropdown
              menu={{
                items: menuItems,
                onClick: ({ key }) => {
                  if (key === 'logout') void logout()
                },
              }}
              placement="bottomRight"
              trigger={['click']}
            >
              <button
                type="button"
                className="flex items-center gap-2 px-1.5 py-1 rounded-sm hover:bg-surface-3 transition-colors"
                aria-label="账号菜单"
              >
                <Avatar size={26} style={{ background: 'var(--primary)', fontSize: 12 }}>
                  {(user.nickname || user.username).slice(0, 1).toUpperCase()}
                </Avatar>
                <span className="hidden sm:inline text-[13.5px] text-ink-2 max-w-[100px] truncate">
                  {user.nickname || user.username}
                </span>
              </button>
            </Dropdown>
          ) : (
            <div className="flex items-center gap-2">
              <Link to={PATHS.login} className="no-underline">
                <Button type="text" size="small">
                  登录
                </Button>
              </Link>
              <Link to={PATHS.register} className="no-underline hidden sm:inline-block">
                <Button type="primary" size="small">
                  注册
                </Button>
              </Link>
            </div>
          )}
        </div>
      </header>

      {/* ── 内容容器 ───────────────────────────────────────── */}
      <main id="main" className="flex-1 mx-auto w-full max-w-[1200px] px-4 sm:px-6 py-6 sm:py-8">
        <Outlet />
      </main>

      {/* ── 页脚 ───────────────────────────────────────────── */}
      <footer className="border-t border-line bg-surface" role="contentinfo">
        <div className="mx-auto max-w-[1200px] px-4 sm:px-6 py-5 flex flex-col sm:flex-row gap-2 sm:items-center sm:justify-between text-[12.5px] text-ink-3">
          <p className="m-0">
            海瞳鱼鉴 · 基于 CNN 的海洋鱼类图像分类系统
          </p>
          <p className="m-0">
            识别结果仅供学习参考，不构成科研或商业决策依据 ·{' '}
            <Link to={PATHS.about} className="text-ink-2 underline underline-offset-2">
              查看免责声明
            </Link>
          </p>
        </div>
      </footer>

      {/* 移动端抽屉导航 */}
      {isMobile && <MobileDrawer nav={NAV} />}
    </div>
  )
}

/* ── 顶栏局部组件 ────────────────────────────────────────────── */

function ServiceBadge({ ready }: { ready: boolean | null }) {
  if (ready === null) return null
  const ok = ready
  return (
    <span
      className={[
        'hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[12.5px]',
        ok ? 'bg-ok-50 text-ok' : 'bg-warn-50 text-warn',
      ].join(' ')}
      title={ok ? '识别服务运行正常' : '识别服务暂不可用'}
    >
      <span
        aria-hidden="true"
        className="w-1.5 h-1.5 rounded-full"
        style={{ background: ok ? 'var(--success)' : 'var(--warn)' }}
      />
      {ok ? '服务正常' : '服务维护中'}
    </span>
  )
}

function BrandMark() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      style={{ color: 'var(--primary)' }}
    >
      <path
        d="M2.5 12c2.8-4.6 6.2-6.9 10.2-6.9 3.2 0 6.2 1.5 8.8 4.6-2.6 3.1-5.6 4.6-8.8 4.6-4 0-7.4-2.3-10.2-6.9Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <circle cx="10.2" cy="12" r="2.4" stroke="currentColor" strokeWidth="1.7" />
      <path d="M2.5 12 21 12" stroke="currentColor" strokeWidth="1.7" opacity=".35" />
    </svg>
  )
}

function HamburgerIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3.5 6.5h17M3.5 12h17M3.5 17.5h17"
        stroke="currentColor"
        strokeWidth="1.9"
        strokeLinecap="round"
      />
    </svg>
  )
}
