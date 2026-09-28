/**
 * 移动端抽屉导航
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §8.2.2（抽屉导航规格）、§8.2.4（移动端不提供的功能）
 *
 * 规格要点：
 *   · 宽度 78vw（最大 320px），从左侧滑入
 *   · 遮罩点击关闭、Esc 关闭、路由变化自动关闭
 *   · 焦点陷阱（AntD Drawer 原生支持）
 *   · 触控目标 ≥ 44px
 * ────────────────────────────────────────────────────────────────
 */

import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Drawer } from 'antd'
import { useUiStore } from '@/stores/uiStore'
import { useAuthStore } from '@/stores/authStore'
import { PATHS } from '@/routes/paths'

interface NavItem {
  readonly to: string
  readonly label: string
}

export default function MobileDrawer({ nav }: { nav: readonly NavItem[] }) {
  const open = useUiStore((s) => s.drawerOpen)
  const close = useUiStore((s) => s.closeDrawer)
  const location = useLocation()

  const isLoggedIn = useAuthStore((s) => s.isLoggedIn())
  const isAdmin = useAuthStore((s) => s.isAdmin())
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const guestQuota = useAuthStore((s) => s.guestQuota)

  // 路由变化时自动关闭抽屉（避免返回时抽屉仍开）
  useEffect(() => {
    close()
  }, [location.pathname, close])

  const linkCls = (active: boolean) =>
    [
      'flex items-center min-h-[44px] px-3 rounded-sm text-[14.5px] no-underline',
      active ? 'bg-brand-50 text-brand font-semibold' : 'text-ink-2',
    ].join(' ')

  return (
    <Drawer
      open={open}
      onClose={close}
      placement="left"
      width="min(78vw, 320px)"
      closable={false}
      styles={{ body: { padding: 12 } }}
      title={
        <div className="flex items-center gap-2">
          <span className="font-semibold text-ink">海瞳鱼鉴</span>
          {!isLoggedIn && guestQuota && (
            <span className="ml-auto text-[12px] px-2 py-0.5 rounded-full bg-brand-50 text-brand">
              剩余 <b className="num">{guestQuota.remaining}</b> 次
            </span>
          )}
        </div>
      }
    >
      <nav className="flex flex-col gap-0.5" aria-label="主导航">
        {nav.map((n) => {
          const active =
            n.to === PATHS.home
              ? location.pathname === PATHS.home
              : location.pathname.startsWith(n.to)
          return (
            <Link
              key={n.to}
              to={n.to}
              className={linkCls(active)}
              onClick={close}
              aria-current={active ? 'page' : undefined}
            >
              {n.label}
            </Link>
          )
        })}
      </nav>

      <div className="my-3 border-t border-line" />

      {isLoggedIn ? (
        <div className="flex flex-col gap-0.5">
          <div className="px-3 py-2 text-[12.5px] text-ink-3">
            已登录：{user?.nickname || user?.username}
          </div>
          <Link to={PATHS.profile} className={linkCls(location.pathname === PATHS.profile)} onClick={close}>
            个人中心
          </Link>
          {isAdmin && (
            <>
              <Link to={PATHS.adminUsers} className={linkCls(location.pathname === PATHS.adminUsers)} onClick={close}>
                用户管理
              </Link>
              <Link to={PATHS.adminRecords} className={linkCls(location.pathname === PATHS.adminRecords)} onClick={close}>
                记录管理
              </Link>
              <Link to={PATHS.adminConfig} className={linkCls(location.pathname === PATHS.adminConfig)} onClick={close}>
                系统配置
              </Link>
            </>
          )}
          <button
            type="button"
            className="flex items-center min-h-[44px] px-3 rounded-sm text-[14.5px] text-danger text-left bg-transparent border-0"
            onClick={() => {
              close()
              void logout()
            }}
          >
            退出登录
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-2 px-3">
          <Link to={PATHS.login} className="no-underline" onClick={close}>
            <button
              type="button"
              className="w-full min-h-[44px] rounded-sm border border-line-strong bg-surface text-[14.5px] text-ink"
            >
              登录
            </button>
          </Link>
          <Link to={PATHS.register} className="no-underline" onClick={close}>
            <button
              type="button"
              className="w-full min-h-[44px] rounded-sm text-[14.5px] text-white"
              style={{ background: 'var(--primary)' }}
            >
              注册
            </button>
          </Link>
        </div>
      )}
    </Drawer>
  )
}
