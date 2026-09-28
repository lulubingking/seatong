/**
 * 页面 13 · 404 兜底 `*`（视图 `notFound`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.13
 *
 * 需求锚点：无（属 PRD §5.2 页面清单兜底项）
 *
 * 【双重用途】
 *   1. 未知路由 → 展示本页
 *   2. 非管理员访问 `/admin/*` → 守卫**渲染本页**而非跳转
 *      （D9 §10.3.2「不暴露管理入口存在性」）
 *      故本页文案不得暗示「权限」或「管理」字样，避免泄露路由存在性。
 * ────────────────────────────────────────────────────────────────
 */

import { Link, useNavigate } from 'react-router-dom'
import { Button } from 'antd'
import { PATHS } from '@/routes/paths'

export default function NotFound() {
  const navigate = useNavigate()

  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-5">
      <p
        className="m-0 text-[56px] font-semibold num leading-none"
        style={{ color: 'var(--border-strong)' }}
        aria-hidden="true"
      >
        404
      </p>

      <h1 className="m-0 mt-4 text-[18px] font-semibold text-ink">页面不存在</h1>

      <p className="m-0 mt-2.5 max-w-[400px] text-[13.5px] leading-[1.7] text-ink-2">
        你访问的地址可能已经变更、被删除，或者链接本身有拼写错误。
      </p>

      <div className="mt-6 flex flex-wrap gap-3 justify-center">
        <Link to={PATHS.home} className="no-underline">
          <Button type="primary">返回首页</Button>
        </Link>
        <Button onClick={() => navigate(-1)}>回到上一页</Button>
      </div>
    </div>
  )
}
