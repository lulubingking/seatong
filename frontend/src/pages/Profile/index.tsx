/**
 * 页面 9 · 个人中心 `/profile`（视图 `profile`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.9
 *
 * 需求锚点：FR-USER-03～05、BR-USER-08、BR-USER-14、BR-USER-15
 *
 * 布局骨架：
 *   ① 账号概览（头像 / 昵称 / 角色 / 注册时间）
 *   ② 资料编辑（昵称、邮箱）
 *   ③ 修改密码（旧密码、新密码、确认）
 *   ④ 我的数据（识别记录数、快捷入口）
 *
 * 注意：本系统**不做密码找回**（PRD 决策基线），故密码区的引导文案
 * 须指向「联系管理员」，不得出现「忘记密码」链接。
 * ────────────────────────────────────────────────────────────────
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Input, Form, Avatar } from 'antd'
import * as usersApi from '@/api/users'
import { isApiError } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { toastOk, toastError } from '@/stores/uiStore'
import { PATHS } from '@/routes/paths'
import { PASSWORD_MIN_LENGTH, USERNAME_MAX_LENGTH } from '@/constants/limits'
import { passwordStrength } from '@/utils/validate'
import Card from '@/components/base/Card'
import Tag from '@/components/base/Tag'
import Alert from '@/components/feedback/Alert'
import { formatDateTime } from '@/utils/format'

export default function Profile() {
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const logout = useAuthStore((s) => s.logout)

  const [profileForm] = Form.useForm<{ nickname?: string; email?: string }>()
  const [pwdForm] = Form.useForm<{ old_password: string; new_password: string; confirm: string }>()
  const [savingProfile, setSavingProfile] = useState(false)
  const [savingPwd, setSavingPwd] = useState(false)
  const [pwdError, setPwdError] = useState<string | null>(null)
  const [newPwd, setNewPwd] = useState('')

  // 把当前用户资料回填表单
  useEffect(() => {
    if (user) {
      profileForm.setFieldsValue({ nickname: user.nickname ?? '', email: user.email ?? '' })
    }
  }, [user, profileForm])

  const saveProfile = async (v: { nickname?: string; email?: string }) => {
    setSavingProfile(true)
    try {
      const next = await usersApi.updateMe({
        nickname: v.nickname?.trim() || null,
        email: v.email?.trim() || null,
      })
      setUser(next)
      toastOk('资料已更新')
    } catch (e) {
      if (isApiError(e) && e.level === 'field') {
        profileForm.setFields([{ name: 'nickname', errors: [e.message] }])
      } else {
        toastError(isApiError(e) ? e.message : '保存失败，请稍后重试')
      }
    } finally {
      setSavingProfile(false)
    }
  }

  const savePassword = async (v: { old_password: string; new_password: string; confirm: string }) => {
    setSavingPwd(true)
    setPwdError(null)
    try {
      await usersApi.changeMyPassword({
        old_password: v.old_password,
        new_password: v.new_password,
      })
      toastOk('密码已修改，请使用新密码重新登录', 4000)
      pwdForm.resetFields()
      setNewPwd('')
      // 改密后令牌可能失效，主动登出更安全
      await logout()
    } catch (e) {
      if (isApiError(e)) {
        if (e.code === '40103' || e.code === '40001') {
          pwdForm.setFields([{ name: 'old_password', errors: [e.message] }])
        } else {
          setPwdError(e.message)
        }
      } else {
        setPwdError('网络连接异常，请检查网络后重试')
      }
    } finally {
      setSavingPwd(false)
    }
  }

  if (!user) return null

  const strength = passwordStrength(newPwd)
  const STRENGTH_META = [
    { label: '', color: 'var(--border-strong)' },
    { label: '弱', color: 'var(--danger)' },
    { label: '一般', color: 'var(--warn)' },
    { label: '较强', color: 'var(--accent)' },
    { label: '强', color: 'var(--success)' },
  ] as const
  const sm = STRENGTH_META[strength]!

  return (
    <div className="flex flex-col gap-5">
      <h1 className="m-0 text-[22px] font-semibold text-ink">个人中心</h1>

      {/* ── ① 账号概览 ────────────────────────────────────── */}
      <Card>
        <div className="flex items-center gap-4">
          <Avatar size={56} style={{ background: 'var(--primary)', fontSize: 22 }}>
            {(user.nickname || user.username).slice(0, 1).toUpperCase()}
          </Avatar>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="m-0 text-[17px] font-semibold text-ink">
                {user.nickname || user.username}
              </p>
              <Tag tone={user.role === 'admin' ? 'brand' : 'muted'}>
                {user.role === 'admin' ? '管理员' : '普通用户'}
              </Tag>
              <Tag tone="ok" dot>
                正常
              </Tag>
            </div>
            <p className="m-0 mt-1.5 text-[13px] text-ink-2">
              账号名 <b className="num">{user.username}</b>（注册后不可修改）
            </p>
            <p className="m-0 mt-0.5 text-[12.5px] text-ink-3 num">
              注册于 {formatDateTime(user.created_at)}
            </p>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-line flex flex-wrap gap-2.5">
          <Link to={PATHS.history} className="no-underline">
            <Button>我的识别记录</Button>
          </Link>
          <Link to={PATHS.recognize} className="no-underline">
            <Button>去识别一张</Button>
          </Link>
          {user.role === 'admin' && (
            <>
              <Link to={PATHS.adminUsers} className="no-underline">
                <Button>用户管理</Button>
              </Link>
              <Link to={PATHS.adminConfig} className="no-underline">
                <Button>系统配置</Button>
              </Link>
            </>
          )}
        </div>
      </Card>

      {/* ── ② 资料编辑 ────────────────────────────────────── */}
      <Card title="基本资料" description="昵称用于界面显示，邮箱仅作账号识别之用。">
        <Form form={profileForm} layout="vertical" onFinish={saveProfile} requiredMark={false}>
          <div className="grid gap-x-5 grid-cols-1 sm:grid-cols-2">
            <Form.Item label="昵称" name="nickname" rules={[{ max: 20, message: '昵称最多 20 个字符' }]}>
              <Input placeholder="留空则显示账号名" maxLength={USERNAME_MAX_LENGTH} />
            </Form.Item>
            <Form.Item
              label="邮箱"
              name="email"
              rules={[{ type: 'email', message: '邮箱地址格式不正确' }]}
            >
              <Input placeholder="选填" autoComplete="email" />
            </Form.Item>
          </div>
          <Button type="primary" htmlType="submit" loading={savingProfile}>
            保存资料
          </Button>
        </Form>
      </Card>

      {/* ── ③ 修改密码 ────────────────────────────────────── */}
      <Card title="修改密码" description="修改成功后需要使用新密码重新登录。">
        {pwdError && (
          <Alert tone="danger" className="mb-4">
            {pwdError}
          </Alert>
        )}

        <Form form={pwdForm} layout="vertical" onFinish={savePassword} requiredMark={false}>
          <Form.Item
            label="当前密码"
            name="old_password"
            rules={[{ required: true, message: '请输入当前密码' }]}
          >
            <Input.Password placeholder="请输入当前使用的密码" autoComplete="current-password" />
          </Form.Item>

          <Form.Item
            label="新密码"
            name="new_password"
            rules={[
              { required: true, message: '请输入新密码' },
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
              placeholder={`至少 ${PASSWORD_MIN_LENGTH} 位，含字母和数字`}
              autoComplete="new-password"
              onChange={(e) => setNewPwd(e.target.value)}
            />
          </Form.Item>

          {newPwd && (
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
            label="确认新密码"
            name="confirm"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请再次输入新密码' },
              ({ getFieldValue }) => ({
                validator: (_, v: string) =>
                  !v || getFieldValue('new_password') === v
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次输入的密码不一致')),
              }),
            ]}
          >
            <Input.Password placeholder="再次输入新密码" autoComplete="new-password" />
          </Form.Item>

          <Button type="primary" htmlType="submit" loading={savingPwd}>
            修改密码
          </Button>
        </Form>

        <Alert tone="info" className="mt-4">
          本系统不提供密码找回功能。若忘记密码，请联系系统管理员协助重置，
          管理员无法查看你的原密码，只能设置一个新的。
        </Alert>
      </Card>

      {/* ── ④ 账号安全提示 ────────────────────────────────── */}
      <Card title="退出登录">
        <p className="m-0 mb-3.5 text-[13.5px] leading-[1.7] text-ink-2">
          退出后当前会话失效，需重新输入账号密码登录。本机保存的登录状态会被清除。
        </p>
        <Button danger onClick={() => void logout()}>
          退出登录
        </Button>
      </Card>
    </div>
  )
}
