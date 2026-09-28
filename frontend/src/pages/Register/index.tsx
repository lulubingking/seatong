/**
 * 页面 5 · 注册 `/register`（视图 `register`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.5
 *
 * 需求锚点：FR-USER-01、FR-USER-04、BR-USER-01～05、BR-USER-14
 *
 * 客户端校验（§5.5）：
 *   账号名 3–32 字符，限字母/数字/下划线
 *   密码 ≥8 位，须同时含字母与数字；带强度条
 *   确认密码须一致
 *   邮箱可选，格式校验
 *
 * 【注册后不自动登录】后端返回用户信息但不返回 token，
 * 故注册成功后跳转登录页并携带账号名预填。
 * ────────────────────────────────────────────────────────────────
 */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, Input, Form } from 'antd'
import { useAuthStore } from '@/stores/authStore'
import { toastOk } from '@/stores/uiStore'
import { PATHS } from '@/routes/paths'
import { isApiError } from '@/api/client'
import {
  PASSWORD_MIN_LENGTH,
  USERNAME_MAX_LENGTH,
  USERNAME_MIN_LENGTH,
} from '@/constants/limits'
import { passwordStrength } from '@/utils/validate'
import Card from '@/components/base/Card'
import Alert from '@/components/feedback/Alert'

interface FormValues {
  username: string
  password: string
  confirm: string
  nickname?: string
  email?: string
}

export default function Register() {
  const register = useAuthStore((s) => s.register)
  const navigate = useNavigate()

  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [pwd, setPwd] = useState('')
  const strength = passwordStrength(pwd)

  const onFinish = async (v: FormValues) => {
    setSubmitting(true)
    setFormError(null)
    try {
      await register(v.username.trim(), v.password, v.nickname?.trim() || undefined, v.email?.trim() || undefined)
      toastOk('注册成功，请使用新账号登录', 3500)
      // 跳转登录页并预填账号
      navigate(`${PATHS.login}?username=${encodeURIComponent(v.username.trim())}`, { replace: true })
    } catch (e) {
      if (!isApiError(e)) {
        setFormError('网络连接异常，请检查网络后重试')
        return
      }
      // 40901 账号名重复 → 指向 username 字段（字段级）
      if (e.code === '40901') {
        form.setFields([{ name: 'username', errors: [e.message] }])
        setFormError(null)
      } else {
        setFormError(e.message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  const STRENGTH_META = [
    { label: '', color: 'var(--border-strong)' },
    { label: '弱', color: 'var(--danger)' },
    { label: '一般', color: 'var(--warn)' },
    { label: '较强', color: 'var(--accent)' },
    { label: '强', color: 'var(--success)' },
  ] as const
  const sm = STRENGTH_META[strength]!

  return (
    <Card>
      <div className="mb-5">
        <h1 className="m-0 text-[19px] font-semibold text-ink">注册新账号</h1>
        <p className="m-0 mt-1.5 text-[13px] text-ink-2">
          注册后可不限次数识别，并保存全部历史记录。
        </p>
      </div>

      {formError && (
        <Alert tone="danger" className="mb-4">
          {formError}
        </Alert>
      )}

      <Form form={form} layout="vertical" onFinish={onFinish} requiredMark={false} disabled={submitting}>
        <Form.Item
          label="账号名"
          name="username"
          rules={[
            { required: true, message: '请输入账号名' },
            { min: USERNAME_MIN_LENGTH, message: `账号名至少 ${USERNAME_MIN_LENGTH} 个字符` },
            { max: USERNAME_MAX_LENGTH, message: `账号名最多 ${USERNAME_MAX_LENGTH} 个字符` },
            { pattern: /^[A-Za-z0-9_]+$/, message: '账号名只能包含字母、数字和下划线' },
          ]}
          extra={
            <span className="text-[12px] text-ink-3">
              支持字母、数字、下划线，注册后不可修改
            </span>
          }
        >
          <Input size="large" placeholder="例如 fishwatcher" autoComplete="username" autoFocus />
        </Form.Item>

        <Form.Item
          label="密码"
          name="password"
          rules={[
            { required: true, message: '请输入密码' },
            { min: PASSWORD_MIN_LENGTH, message: `密码至少 ${PASSWORD_MIN_LENGTH} 位` },
            {
              validator: (_, v: string) =>
                !v || (/[A-Za-z]/.test(v) && /\d/.test(v))
                  ? Promise.resolve()
                  : Promise.reject(new Error('密码须同时包含字母和数字')),
            },
          ]}
        >
          <Input.Password
            size="large"
            placeholder={`至少 ${PASSWORD_MIN_LENGTH} 位，含字母和数字`}
            autoComplete="new-password"
            onChange={(e) => setPwd(e.target.value)}
          />
        </Form.Item>

        {/* 密码强度条 */}
        {pwd && (
          <div className="-mt-3 mb-4">
            <div className="flex gap-1" aria-hidden="true">
              {[1, 2, 3, 4].map((i) => (
                <span
                  key={i}
                  className="flex-1 transition-colors"
                  style={{
                    height: 4,
                    borderRadius: 999,
                    background: i <= strength ? sm.color : 'var(--surface-3)',
                  }}
                />
              ))}
            </div>
            <p className="m-0 mt-1 text-[12px]" style={{ color: sm.color || 'var(--text-3)' }}>
              密码强度：{sm.label || '过弱'}
            </p>
          </div>
        )}

        <Form.Item
          label="确认密码"
          name="confirm"
          dependencies={['password']}
          rules={[
            { required: true, message: '请再次输入密码' },
            ({ getFieldValue }) => ({
              validator: (_, v: string) =>
                !v || getFieldValue('password') === v
                  ? Promise.resolve()
                  : Promise.reject(new Error('两次输入的密码不一致')),
            }),
          ]}
        >
          <Input.Password size="large" placeholder="再次输入密码" autoComplete="new-password" />
        </Form.Item>

        <Form.Item label="昵称（可选）" name="nickname">
          <Input size="large" placeholder="用于界面显示，留空则显示账号名" maxLength={20} />
        </Form.Item>

        <Form.Item
          label="邮箱（可选）"
          name="email"
          rules={[{ type: 'email', message: '邮箱地址格式不正确' }]}
        >
          <Input size="large" placeholder="仅用于账号识别，不发送邮件" autoComplete="email" />
        </Form.Item>

        <Button type="primary" size="large" block htmlType="submit" loading={submitting}>
          注册
        </Button>
      </Form>

      <div className="mt-4 pt-4 border-t border-line text-center text-[13px]">
        <span className="text-ink-2">
          已有账号？
          <Link to={PATHS.login} className="ml-1 text-brand underline underline-offset-2">
            去登录
          </Link>
        </span>
      </div>
    </Card>
  )
}
