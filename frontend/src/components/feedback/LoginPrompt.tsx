/**
 * 登录引导弹窗
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §6.2（额度门禁判定流程）、§5.6（游客额度耗尽）
 *
 * 触发时机（仅两种）：
 *   · `40101` 请先登录后再操作 —— 用户试图执行**写操作**时
 *   · `42901` 试用次数已用完，登录后可继续使用
 *
 * 【关键】不是「令牌过期就弹」—— 令牌过期只做静默降级（Toast 轻提示）。
 * 只有用户主动尝试需要登录的操作时才弹出，避免登录页反复骚扰。
 *
 * 【保留上下文】弹窗关闭后，用户先前在识别工作台选的图片、填的表单都不丢
 * —— 本组件不改动任何业务 store，只开关一个布尔。
 * ────────────────────────────────────────────────────────────────
 */

import { useLocation, useNavigate } from 'react-router-dom'
import { Modal, Button } from 'antd'
import { useAuthStore } from '@/stores/authStore'
import { PATHS } from '@/routes/paths'

export default function LoginPrompt() {
  const open = useAuthStore((s) => s.loginPromptOpen)
  const reason = useAuthStore((s) => s.loginPromptReason)
  const close = useAuthStore((s) => s.closeLoginPrompt)
  const navigate = useNavigate()
  const location = useLocation()

  const go = (to: string) => {
    close()
    // 携带当前路径，登录成功后回到原处（D9 §10.3.2 重定向白名单）
    const redirect = encodeURIComponent(location.pathname + location.search)
    navigate(`${to}?redirect=${redirect}`)
  }

  return (
    <Modal
      open={open}
      onCancel={close}
      footer={null}
      centered
      width={400}
      title={null}
      // 弹窗是最外层卡片，圆角用 --radius-lg（14px，D9 §3.8）
      styles={{ content: { borderRadius: 'var(--radius-lg)', padding: 0 } }}
    >
      <div className="px-6 pt-6 pb-5 text-center">
        <div
          className="mx-auto mb-3.5 w-11 h-11 rounded-full flex items-center justify-center"
          style={{ background: 'var(--primary-50)' }}
          aria-hidden="true"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" style={{ color: 'var(--primary)' }}>
            <circle cx="12" cy="8.5" r="3.6" stroke="currentColor" strokeWidth="1.9" />
            <path
              d="M4.8 20.2c.5-3.7 3.5-5.6 7.2-5.6s6.7 1.9 7.2 5.6"
              stroke="currentColor"
              strokeWidth="1.9"
              strokeLinecap="round"
            />
          </svg>
        </div>

        <h2 className="text-[16.5px] font-semibold text-ink m-0 mb-1.5">
          {reason || '请先登录后再操作'}
        </h2>
        <p className="text-[13.5px] text-ink-2 m-0 mb-5 leading-[1.6]">
          登录后可无限次识别、保存历史记录，
          <br />
          并随时回看往次结果。你的当前操作不会丢失。
        </p>

        <div className="flex flex-col gap-2.5">
          <Button type="primary" size="large" block onClick={() => go(PATHS.login)}>
            前往登录
          </Button>
          <Button size="large" block onClick={() => go(PATHS.register)}>
            还没有账号？立即注册
          </Button>
          <button
            type="button"
            className="mt-1 text-[13px] text-ink-3 bg-transparent border-0 underline underline-offset-2"
            onClick={close}
          >
            暂不登录，继续浏览
          </button>
        </div>
      </div>
    </Modal>
  )
}
