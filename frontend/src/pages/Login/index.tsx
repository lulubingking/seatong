/**
 * 页面 4 · 登录 `/login`（视图 `login`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.4
 *
 * 需求锚点：FR-USER-02、FR-USER-03、BR-USER-06、BR-USER-07、BR-USER-15
 *
 * 错误处理（§5.4 字段级文案）：
 *   40103 账号或密码错误 → 表单顶部 Alert；**清空密码、保留账号**
 *   40104 账号已禁用     → 停留本页，不写 token
 *   40105 账号已锁定     → 展示剩余时间，按钮倒计时禁用
 *   40001 参数错误       → 聚焦首个非法字段
 *
 * 【重定向白名单】登录成功后读取 `?redirect=`，仅接受站内路径（§10.3.2）。
 * ────────────────────────────────────────────────────────────────
 */

import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Input, Form } from 'antd'
import { useAuthStore } from '@/stores/authStore'
import { toastOk } from '@/stores/uiStore'
import { safeRedirect } from '@/routes/guards'
import { PATHS } from '@/routes/paths'
import { isApiError } from '@/api/client'
import Card from '@/components/base/Card'
import Alert from '@/components/feedback/Alert'

export default function Login() {
  const login = useAuthStore((s) => s.login)
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const [form] = Form.useForm<{ username: string; password: string }>()
  const [submitting, setSubmitting] = useState(false)
  /** 表单级错误（40103 / 40104 —— 不指向具体字段） */
  const [formError, setFormError] = useState<string | null>(null)
  /** 锁定倒计时（40105），单位秒 */
  const [lockLeft, setLockLeft] = useState(0)
  const timerRef = useRef<number | null>(null)
  /** 需要聚焦的字段名（40001 → 聚焦首个非法字段） */
  const [focusField, setFocusField] = useState<string | null>(null)

  // 锁定倒计时
  useEffect(() => {
    if (lockLeft <= 0) {
      if (timerRef.current) window.clearInterval(timerRef.current)
      return
    }
    timerRef.current = window.setInterval(() => {
      setLockLeft((n) => Math.max(0, n - 1))
    }, 1000)
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
    }
  }, [lockLeft])

  // 聚焦首个非法字段
  useEffect(() => {
    if (focusField) {
      form.getFieldInstance(focusField)?.focus?.()
      setFocusField(null)
    }
  }, [focusField, form])

  const onFinish = async (v: { username: string; password: string }) => {
    setSubmitting(true)
    setFormError(null)
    try {
      await login(v.username.trim(), v.password)
      toastOk('登录成功', 2500)
      const target = safeRedirect(params.get('redirect'))
      navigate(target, { replace: true })
    } catch (e) {
      if (!isApiError(e)) {
        setFormError('网络连接异常，请检查网络后重试')
        return
      }
      switch (e.code) {
        case '40103':
          // 顶部 Alert；清密码留账号
          setFormError(e.message)
          form.setFieldValue('password', '')
          form.getFieldInstance('password')?.focus?.()
          break
        case '40104':
          setFormError(e.message)
          break
        case '40105': {
          setFormError(e.message)
          // 从文案中解析剩余分钟数并启动倒计时
          const m = /(\d+)\s*分钟/.exec(e.message)
          setLockLeft((m ? Number(m[1]) : 5) * 60)
          break
        }
        case '40001':
          setFormError(null)
          setFocusField('username')
          break
        default:
          setFormError(e.message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  const locked = lockLeft > 0

  return (
    <Card>
      <div className="mb-5">
        <h1 className="m-0 text-[19px] font-semibold text-ink">登录账号</h1>
        <p className="m-0 mt-1.5 text-[13px] text-ink-2">
          登录后可不限次数识别，并保存历史记录。
        </p>
      </div>

      {formError && (
        <Alert tone={locked ? 'warn' : 'danger'} className="mb-4">
          {formError}
          {locked && (
            <>
              {' '}
              <b className="num">{Math.floor(lockLeft / 60)}</b> 分{' '}
              <b className="num">{lockLeft % 60}</b> 秒后可重试
            </>
          )}
        </Alert>
      )}

      <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false} disabled={submitting}>
        <Form.Item
          label="账号名"
          name="username"
          rules={[{ required: true, message: '请输入账号名' }]}
        >
          <Input size="large" placeholder="请输入账号名" autoComplete="username" autoFocus />
        </Form.Item>

        <Form.Item
          label="密码"
          name="password"
          rules={[{ required: true, message: '请输入密码' }]}
        >
          <Input.Password size="large" placeholder="请输入密码" autoComplete="current-password" />
        </Form.Item>

        <Button
          type="primary"
          size="large"
          block
          htmlType="submit"
          loading={submitting}
          disabled={locked}
          className="mt-1"
        >
          {locked ? `请等待 ${lockLeft} 秒` : '登录'}
        </Button>
      </Form>

      <div className="mt-4 pt-4 border-t border-line flex flex-col items-center gap-2 text-[13px]">
        <span className="text-ink-2">
          还没有账号？
          <Link to={PATHS.register} className="ml-1 text-brand underline underline-offset-2">
            立即注册
          </Link>
        </span>
        <Link to={PATHS.recognize} className="text-ink-3 underline underline-offset-2">
          先以游客身份试用
        </Link>
      </div>

      <Alert tone="info" className="mt-4">
        本系统不提供密码找回功能。请妥善保管账号密码，
        如忘记密码请联系系统管理员协助重置。
      </Alert>
    </Card>
  )
}
