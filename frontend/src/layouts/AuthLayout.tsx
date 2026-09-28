/**
 * 登录/注册页专用框架（无顶栏与页脚，居中卡片）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §10.3.1（`<AuthLayout>`：无框架，居中卡片）
 *
 * 视觉：整页 `--bg` 底色 + 居中卡片（`--radius-lg` / `--surface` / `--border`）
 * 例外：此布局**不显示**主导航，仅保留左上角返回首页的品牌标识，
 *       避免用户在登录流程中被导航分散注意力。
 * ────────────────────────────────────────────────────────────────
 */

import { Link, Outlet } from 'react-router-dom'
import { PATHS } from '@/routes/paths'

export default function AuthLayout() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-bg px-4 py-8">
      <Link
        to={PATHS.home}
        className="flex items-center gap-2 mb-6 no-underline text-ink font-semibold text-[15px]"
      >
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
        </svg>
        <span>海瞳鱼鉴</span>
      </Link>

      <main id="main" className="w-full max-w-[404px]">
        <Outlet />
      </main>

      <p className="mt-6 mb-0 text-[12.5px] text-ink-3 text-center">
        识别结果仅供学习参考
      </p>
    </div>
  )
}
