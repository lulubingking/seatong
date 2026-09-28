/**
 * 页面 10 · 用户管理 `/admin/users`（视图 `adminUsers`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.10
 *
 * 需求锚点：FR-USER-07～09、BR-USER-09、BR-USER-11、BR-USER-16、BR-USER-17
 *
 * 布局骨架：
 *   ① 标题 + 统计摘要
 *   ② 筛选条（角色 / 状态 / 关键词）+ 新建用户
 *   ③ 用户表格（账号 / 昵称 / 角色 / 状态开关 / 注册时间 / 操作）
 *   ④ 新建 / 编辑弹窗
 *   ⑤ 重置密码弹窗
 *
 * 状态开关的业务规则（后端实测的 3 个 409xx）：
 *   40902 不能禁用**当前登录**的账号     → 开关回弹
 *   40903 须保留**至少一个可用管理员**   → 开关回弹 + 就地说明
 *   40904 只能重置**普通用户**的密码     → 按钮置灰 + title 说明
 * ────────────────────────────────────────────────────────────────
 */

import { useCallback, useEffect, useState } from 'react'
import { Button, Input, Select, Table, Switch, Modal, Form, Popconfirm, Pagination } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import * as usersApi from '@/api/users'
import { isApiError } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { useUiStore } from '@/stores/uiStore'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import { ADMIN_PAGE_SIZE } from '@/constants/limits'
import { USER_ROLE, USER_STATUS, USER_STATUS_META, type UserRole } from '@/constants/enums'
import type { User } from '@/api/types'
import Card from '@/components/base/Card'
import Tag from '@/components/base/Tag'
import Alert from '@/components/feedback/Alert'
import EmptyState from '@/components/data/EmptyState'
import PageSkeleton from '@/components/feedback/PageSkeleton'
import { formatDateTime } from '@/utils/format'

export default function AdminUsers() {
  const { isMobile } = useBreakpoint()
  const me = useAuthStore((s) => s.user)
  const toastOk = useUiStore((s) => s.toast)
  const toastErr = useUiStore((s) => s.toast)

  const [items, setItems] = useState<User[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [keyword, setKeyword] = useState('')
  const [roleFilter, setRoleFilter] = useState<UserRole | undefined>()
  const [statusFilter, setStatusFilter] = useState<number | undefined>()

  const [editTarget, setEditTarget] = useState<User | null | 'new'>(null)
  const [pwdTarget, setPwdTarget] = useState<User | null>(null)
  const [switching, setSwitching] = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const out = await usersApi.listUsers({
        page,
        page_size: ADMIN_PAGE_SIZE,
        keyword: keyword.trim() || undefined,
        role: roleFilter,
        status: statusFilter,
      })
      setItems(out.items)
      setTotal(out.total)
    } catch (e) {
      setErr(isApiError(e) ? e.message : '用户列表加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [page, keyword, roleFilter, statusFilter])

  useEffect(() => {
    void load()
  }, [load])

  /* ── 启停开关 ────────────────────────────────────────────── */
  const toggleStatus = async (u: User, next: boolean) => {
    setSwitching(u.id)
    try {
      await usersApi.updateUser(u.id, { status: next ? USER_STATUS.ACTIVE : USER_STATUS.DISABLED })
      toastOk(next ? `已启用「${u.username}」` : `已禁用「${u.username}」`)
      void load()
    } catch (e) {
      // 40902 / 40903 为区块级 → 就地 Alert 提示，开关回弹（不乐观更新，UI 自然回到原状）
      toastErr(isApiError(e) ? e.message : '操作失败，请稍后重试', 'danger', 4500)
    } finally {
      setSwitching(null)
    }
  }

  const remove = async (u: User) => {
    try {
      await usersApi.deleteUser(u.id)
      toastOk(`已删除用户「${u.username}」`)
      void load()
    } catch (e) {
      toastErr(isApiError(e) ? e.message : '删除失败，请稍后重试', 'danger')
    }
  }

  const isSelf = (u: User) => me?.id === u.id
  const isLastAdmin = (u: User) =>
    u.role === USER_ROLE.ADMIN &&
    items.filter((x) => x.role === USER_ROLE.ADMIN && x.status === USER_STATUS.ACTIVE).length <= 1

  const columns: ColumnsType<User> = [
    {
      title: '账号名',
      dataIndex: 'username',
      render: (_: unknown, u) => (
        <div className="min-w-0">
          <p className="m-0 text-[13.5px] font-medium text-ink truncate num">{u.username}</p>
          {isSelf(u) && (
            <span className="text-[11.5px] text-brand">当前登录账号</span>
          )}
        </div>
      ),
    },
    {
      title: '昵称',
      dataIndex: 'nickname',
      render: (v: string | null) => <span className="text-ink-2 text-[13px]">{v || '—'}</span>,
    },
    {
      title: '角色',
      dataIndex: 'role',
      width: 104,
      render: (v: UserRole) => (
        <Tag tone={v === USER_ROLE.ADMIN ? 'brand' : 'muted'}>
          {v === USER_ROLE.ADMIN ? '管理员' : '普通用户'}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 148,
      render: (v: number, u) => (
        <div className="flex items-center gap-2">
          <Switch
            size="small"
            checked={v === USER_STATUS.ACTIVE}
            loading={switching === u.id}
            disabled={isSelf(u) || (u.status === USER_STATUS.ACTIVE && isLastAdmin(u))}
            onChange={(next) => void toggleStatus(u, next)}
            aria-label={`${v === USER_STATUS.ACTIVE ? '禁用' : '启用'} ${u.username}`}
          />
          <Tag tone={USER_STATUS_META[v]?.tone ?? 'muted'}>
            {USER_STATUS_META[v]?.label ?? '未知'}
          </Tag>
        </div>
      ),
    },
    {
      title: '注册时间',
      dataIndex: 'created_at',
      width: 168,
      render: (v: number) => <span className="num text-ink-2 text-[12.5px]">{formatDateTime(v)}</span>,
    },
    {
      title: '操作',
      key: 'action',
      width: 176,
      align: 'center',
      render: (_: unknown, u) => {
        const pwdDisabled = u.role === USER_ROLE.ADMIN
        return (
          <div className="flex gap-1 justify-center">
            <Button type="link" size="small" onClick={() => setEditTarget(u)}>
              编辑
            </Button>
            <Button
              type="link"
              size="small"
              disabled={pwdDisabled}
              title={pwdDisabled ? '只能重置普通用户的密码' : undefined}
              onClick={() => setPwdTarget(u)}
            >
              重置密码
            </Button>
            <Popconfirm
              title={`删除用户「${u.username}」？`}
              description="该用户的识别记录也会一并删除，此操作不可撤销。"
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              disabled={isSelf(u)}
              onConfirm={() => void remove(u)}
            >
              <Button type="link" size="small" danger disabled={isSelf(u)} title={isSelf(u) ? '不能删除当前登录的账号' : undefined}>
                删除
              </Button>
            </Popconfirm>
          </div>
        )
      },
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-start gap-3 justify-between">
        <div>
          <h1 className="m-0 text-[22px] font-semibold text-ink">用户管理</h1>
          <p className="m-0 mt-1.5 text-[13.5px] text-ink-2">
            共 <b className="num text-ink">{total}</b> 个账号
          </p>
        </div>
        <Button type="primary" onClick={() => setEditTarget('new')}>
          新建用户
        </Button>
      </header>

      <Card padding="sm">
        <div className="flex flex-wrap gap-3 items-center">
          <Input.Search
            allowClear
            placeholder="搜索账号名或昵称"
            style={{ width: 220 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={() => setPage(1)}
          />
          <Select
            allowClear
            placeholder="全部角色"
            style={{ width: 140 }}
            value={roleFilter}
            onChange={(v) => {
              setRoleFilter(v)
              setPage(1)
            }}
            options={[
              { value: USER_ROLE.ADMIN, label: '管理员' },
              { value: USER_ROLE.USER, label: '普通用户' },
            ]}
          />
          <Select
            allowClear
            placeholder="全部状态"
            style={{ width: 140 }}
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v)
              setPage(1)
            }}
            options={[
              { value: USER_STATUS.ACTIVE, label: '正常' },
              { value: USER_STATUS.DISABLED, label: '已禁用' },
            ]}
          />
        </div>
      </Card>

      {err && (
        <Alert
          tone="danger"
          title="用户列表加载失败"
          action={
            <Button size="small" onClick={() => void load()}>
              重试
            </Button>
          }
        >
          {err}
        </Alert>
      )}

      {loading ? (
        <PageSkeleton variant="table" rows={6} showHeader={false} />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            title="没有符合条件的账号"
            description={
              keyword || roleFilter !== undefined || statusFilter !== undefined
                ? '当前筛选条件下没有找到账号，试试放宽条件。'
                : '系统中还没有任何账号。'
            }
            action={
              keyword || roleFilter !== undefined || statusFilter !== undefined ? (
                <Button
                  onClick={() => {
                    setKeyword('')
                    setRoleFilter(undefined)
                    setStatusFilter(undefined)
                    setPage(1)
                  }}
                >
                  清除筛选
                </Button>
              ) : (
                <Button type="primary" onClick={() => setEditTarget('new')}>
                  新建第一个用户
                </Button>
              )
            }
          />
        </Card>
      ) : isMobile ? (
        <ul className="m-0 p-0 list-none flex flex-col gap-2.5">
          {items.map((u) => (
            <li key={u.id} className="rounded-lg border border-line bg-surface p-3.5">
              <div className="flex items-start gap-2.5">
                <div className="flex-1 min-w-0">
                  <p className="m-0 text-[14px] font-medium text-ink num truncate">{u.username}</p>
                  <p className="m-0 mt-0.5 text-[12.5px] text-ink-2 truncate">{u.nickname || '未设置昵称'}</p>
                </div>
                <Tag tone={u.role === USER_ROLE.ADMIN ? 'brand' : 'muted'}>
                  {u.role === USER_ROLE.ADMIN ? '管理员' : '用户'}
                </Tag>
              </div>
              <div className="mt-2.5 flex items-center gap-2">
                <Switch
                  size="small"
                  checked={u.status === USER_STATUS.ACTIVE}
                  loading={switching === u.id}
                  disabled={isSelf(u) || (u.status === USER_STATUS.ACTIVE && isLastAdmin(u))}
                  onChange={(next) => void toggleStatus(u, next)}
                />
                <span className="text-[12.5px] text-ink-2">{USER_STATUS_META[u.status]?.label}</span>
                <span className="ml-auto text-[11.5px] text-ink-3 num">{formatDateTime(u.created_at)}</span>
              </div>
              <div className="mt-2.5 pt-2.5 border-t border-line flex gap-2">
                <Button size="small" onClick={() => setEditTarget(u)}>
                  编辑
                </Button>
                <Button
                  size="small"
                  disabled={u.role === USER_ROLE.ADMIN}
                  title={u.role === USER_ROLE.ADMIN ? '只能重置普通用户的密码' : undefined}
                  onClick={() => setPwdTarget(u)}
                >
                  重置密码
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <Card padding="none">
          <Table<User>
            rowKey="id"
            size="middle"
            columns={columns}
            dataSource={items}
            pagination={false}
            scroll={{ x: 860 }}
          />
        </Card>
      )}

      {total > ADMIN_PAGE_SIZE && (
        <div className="flex justify-end">
          <Pagination
            current={page}
            pageSize={ADMIN_PAGE_SIZE}
            total={total}
            showTotal={(t) => `共 ${t} 个账号`}
            onChange={setPage}
          />
        </div>
      )}

      <UserEditModal
        target={editTarget}
        onClose={() => setEditTarget(null)}
        onSaved={() => {
          setEditTarget(null)
          void load()
        }}
      />

      <ResetPasswordModal
        target={pwdTarget}
        onClose={() => setPwdTarget(null)}
        onSaved={() => setPwdTarget(null)}
      />
    </div>
  )
}

/* ── 新建 / 编辑弹窗 ─────────────────────────────────────────── */

function UserEditModal({
  target,
  onClose,
  onSaved,
}: {
  target: User | null | 'new'
  onClose: () => void
  onSaved: () => void
}) {
  const [form] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const isNew = target === 'new'
  const open = target !== null
  /** 编辑模式的用户对象（新建或未打开时为 null） */
  const editing: User | null = target !== null && target !== 'new' ? target : null

  useEffect(() => {
    if (!open) return
    if (isNew) form.resetFields()
    else if (editing) {
      form.setFieldsValue({
        username: editing.username,
        nickname: editing.nickname ?? '',
        email: editing.email ?? '',
        role: editing.role,
      })
    }
  }, [open, isNew, editing, form])

  const submit = async () => {
    const v = await form.validateFields()
    setSaving(true)
    try {
      if (isNew) {
        await usersApi.createUser({
          username: v.username.trim(),
          password: v.password,
          nickname: v.nickname?.trim() || undefined,
          email: v.email?.trim() || undefined,
          role: v.role,
        })
      } else if (editing) {
        await usersApi.updateUser(editing.id, {
          nickname: v.nickname?.trim() || null,
          email: v.email?.trim() || null,
          role: v.role,
        })
      }
      onSaved()
    } catch (e) {
      if (isApiError(e)) {
        if (e.code === '40901') {
          form.setFields([{ name: 'username', errors: [e.message] }])
        } else if (e.level === 'field') {
          form.setFields([{ name: 'nickname', errors: [e.message] }])
        } else {
          form.setFields([{ name: 'username', errors: [e.message] }])
        }
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={() => void submit()}
      confirmLoading={saving}
      title={isNew ? '新建用户' : `编辑用户「${editing?.username ?? ''}」`}
      okText={isNew ? '创建' : '保存'}
      cancelText="取消"
      width={440}
      destroyOnClose
      styles={{ content: { borderRadius: 'var(--radius-lg)' } }}
    >
      <Form form={form} layout="vertical" requiredMark={false} className="pt-2">
        {isNew && (
          <>
            <Form.Item
              label="账号名"
              name="username"
              rules={[
                { required: true, message: '请输入账号名' },
                { min: 3, message: '账号名至少 3 个字符' },
                { max: 32, message: '账号名最多 32 个字符' },
                { pattern: /^[A-Za-z0-9_]+$/, message: '账号名只能包含字母、数字和下划线' },
              ]}
            >
              <Input placeholder="字母、数字、下划线" autoComplete="off" />
            </Form.Item>
            <Form.Item
              label="初始密码"
              name="password"
              rules={[
                { required: true, message: '请输入初始密码' },
                { min: 8, message: '密码至少 8 位' },
              ]}
            >
              <Input.Password placeholder="至少 8 位" autoComplete="new-password" />
            </Form.Item>
          </>
        )}

        <Form.Item label="昵称" name="nickname" rules={[{ max: 20, message: '昵称最多 20 个字符' }]}>
          <Input placeholder="选填" />
        </Form.Item>

        <Form.Item label="邮箱" name="email" rules={[{ type: 'email', message: '邮箱地址格式不正确' }]}>
          <Input placeholder="选填" />
        </Form.Item>

        <Form.Item label="角色" name="role" initialValue={USER_ROLE.USER}>
          <Select
            options={[
              { value: USER_ROLE.USER, label: '普通用户' },
              { value: USER_ROLE.ADMIN, label: '管理员' },
            ]}
          />
        </Form.Item>

        {!isNew && (
          <Alert tone="info">
            账号名注册后不可修改。若要停用该账号，请在列表中关闭其状态开关。
          </Alert>
        )}
      </Form>
    </Modal>
  )
}

/* ── 重置密码弹窗 ────────────────────────────────────────────── */

function ResetPasswordModal({
  target,
  onClose,
  onSaved,
}: {
  target: User | null
  onClose: () => void
  onSaved: () => void
}) {
  const [form] = Form.useForm<{ new_password: string }>()
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const open = target !== null

  useEffect(() => {
    if (open) {
      form.resetFields()
      setErr(null)
    }
  }, [open, form])

  const submit = async () => {
    if (!target) return
    const v = await form.validateFields()
    setSaving(true)
    setErr(null)
    try {
      await usersApi.resetUserPassword(target.id, { new_password: v.new_password })
      onSaved()
    } catch (e) {
      setErr(isApiError(e) ? e.message : '重置失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={() => void submit()}
      confirmLoading={saving}
      title={`重置「${target?.username ?? ''}」的密码`}
      okText="确认重置"
      cancelText="取消"
      width={420}
      destroyOnClose
      styles={{ content: { borderRadius: 'var(--radius-lg)' } }}
    >
      {err && (
        <Alert tone="danger" className="mb-4">
          {err}
        </Alert>
      )}
      <Form form={form} layout="vertical" requiredMark={false} className="pt-1">
        <Form.Item
          label="新密码"
          name="new_password"
          rules={[
            { required: true, message: '请输入新密码' },
            { min: 8, message: '密码至少 8 位' },
          ]}
        >
          <Input.Password placeholder="至少 8 位，含字母和数字" autoComplete="new-password" />
        </Form.Item>
      </Form>
      <Alert tone="warn">
        重置后该用户的登录状态会失效，需要使用新密码重新登录。
        系统无法查看用户的原密码。
      </Alert>
    </Modal>
  )
}
