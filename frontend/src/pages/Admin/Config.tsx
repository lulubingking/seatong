/**
 * 页面 12 · 系统配置 `/admin/config`（视图 `adminConfig`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.12
 *
 * 需求锚点：FR-USER-09、BR-USER-18、BR-RECOG-04、BR-PREPROC-02～04、
 *           BR-HISTORY-10、NFR-REL-02、NFR-MAINT-01
 *
 * 布局骨架：
 *   ① 标题 + 说明
 *   ② 配置项列表（每项一行：名称 / 说明 / 当前值 / 编辑）
 *   ③ 逐项编辑（**单点更新**，非整体提交）
 *   ④ 操作日志（折叠面板，默认收起）
 *
 * 【⚠ 端点差异】D9 §10.4.4 写作 `GET/PUT /api/config`（**丢失 admin 前缀**），
 * 后端实际为 `GET /api/admin/config` + `PATCH /api/admin/config/{key}`（单点更新）。
 * 本页按后端实现对接，差异已登记于 `docs/海瞳鱼鉴-接口契约偏离诊断.md`。
 *
 * 【为何改为单点更新】配置项彼此独立，逐项更新可避免「改一项却提交全部」
 * 带来的并发覆盖风险，也让错误定位到具体字段。
 * ────────────────────────────────────────────────────────────────
 */

import { useCallback, useEffect, useState } from 'react'
import { Button, Input, Table, Pagination, Collapse, Modal } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import * as configApi from '@/api/config'
import { isApiError } from '@/api/client'
import { toastOk } from '@/stores/uiStore'
import { ADMIN_PAGE_SIZE } from '@/constants/limits'
import { CONFIG_KEYS } from '@/api/types'
import type { ConfigItem, OperationLog } from '@/api/types'
import Card from '@/components/base/Card'
import Tag from '@/components/base/Tag'
import Alert from '@/components/feedback/Alert'
import EmptyState from '@/components/data/EmptyState'
import PageSkeleton from '@/components/feedback/PageSkeleton'
import { formatDateTime, formatNumber } from '@/utils/format'

/** 配置项的中文名与取值范围（前端只做输入引导，最终以服务端校验为准） */
const CONFIG_META: Record<
  string,
  { label: string; unit?: string; min?: number; max?: number; integer?: boolean; impact: string }
> = {
  [CONFIG_KEYS.GUEST_QUOTA]: {
    label: '游客试用次数',
    unit: '次',
    min: 0,
    max: 999,
    integer: true,
    impact: '调整后仅影响新发起的游客会话，已产生的试用记录不回退。',
  },
  [CONFIG_KEYS.BATCH_UPLOAD_LIMIT]: {
    label: '批量上传张数上限',
    unit: '张',
    min: 1,
    max: 50,
    integer: true,
    impact: '改为较大值会显著增加单次请求的处理时长与显存占用。',
  },
  [CONFIG_KEYS.MAX_FILE_SIZE_MB]: {
    label: '单张图片体积上限',
    unit: 'MB',
    min: 1,
    max: 100,
    integer: true,
    impact: '放宽后需确认磁盘配额充足。',
  },
  [CONFIG_KEYS.IMAGE_RETENTION_DAYS]: {
    label: '上传原图保留天数',
    unit: '天',
    min: 1,
    max: 3650,
    integer: true,
    impact: '缩短保留期会加速清理历史原图，被清理的原图将无法再查看（识别结果不受影响）。',
  },
  [CONFIG_KEYS.LOW_CONFIDENCE_THRESHOLD]: {
    label: '低置信度提示阈值',
    unit: '',
    min: 0,
    max: 1,
    integer: false,
    impact: '取值 0–1。调高会使更多结果被标记为「低置信度」。',
  },
}

export default function AdminConfig() {
  const [items, setItems] = useState<ConfigItem[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const [editing, setEditing] = useState<ConfigItem | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [fieldErr, setFieldErr] = useState<string | null>(null)

  const [logs, setLogs] = useState<OperationLog[]>([])
  const [logTotal, setLogTotal] = useState(0)
  const [logPage, setLogPage] = useState(1)
  const [logLoading, setLogLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      setItems(await configApi.getConfig())
    } catch (e) {
      setErr(isApiError(e) ? e.message : '配置加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const loadLogs = useCallback(async (p: number) => {
    setLogLoading(true)
    try {
      const out = await configApi.listLogs({ page: p, page_size: ADMIN_PAGE_SIZE })
      setLogs(out.items)
      setLogTotal(out.total)
    } catch {
      setLogs([])
      setLogTotal(0)
    } finally {
      setLogLoading(false)
    }
  }, [])

  const openEdit = (c: ConfigItem) => {
    setEditing(c)
    setDraft(c.value)
    setFieldErr(null)
  }

  const submitEdit = async () => {
    if (!editing) return
    const meta = CONFIG_META[editing.config_key]
    const raw = draft.trim()

    // 客户端预校验（只为即时反馈，服务端为准）
    if (raw === '') {
      setFieldErr('请输入配置值')
      return
    }
    const num = Number(raw)
    if (!Number.isFinite(num)) {
      setFieldErr('请输入有效的数字')
      return
    }
    if (meta?.integer && !Number.isInteger(num)) {
      setFieldErr('该项须为整数')
      return
    }
    if (meta?.min !== undefined && num < meta.min) {
      setFieldErr(`取值不能小于 ${meta.min}`)
      return
    }
    if (meta?.max !== undefined && num > meta.max) {
      setFieldErr(`取值不能大于 ${meta.max}`)
      return
    }

    setSaving(true)
    setFieldErr(null)
    try {
      await configApi.updateConfig({ [editing.config_key]: raw })
      toastOk(`「${meta?.label ?? editing.config_key}」已更新`)
      setEditing(null)
      void load()
    } catch (e) {
      if (isApiError(e)) {
        setFieldErr(e.message)
      } else {
        setFieldErr('保存失败，请稍后重试')
      }
    } finally {
      setSaving(false)
    }
  }

  const columns: ColumnsType<ConfigItem> = [
    {
      title: '配置项',
      dataIndex: 'config_key',
      render: (_: unknown, c) => (
        <div className="min-w-0">
          <p className="m-0 text-[13.5px] font-medium text-ink">
            {CONFIG_META[c.config_key]?.label ?? c.config_key}
          </p>
          <p className="m-0 text-[11.5px] text-ink-3 num">{c.config_key}</p>
        </div>
      ),
    },
    {
      title: '当前值',
      dataIndex: 'value',
      width: 148,
      align: 'right',
      render: (_: unknown, c) => (
        <span className="num text-[14px] font-semibold text-ink">
          {c.value}
          {CONFIG_META[c.config_key]?.unit && (
            <span className="ml-0.5 text-[12px] font-normal text-ink-3">
              {CONFIG_META[c.config_key]!.unit}
            </span>
          )}
        </span>
      ),
    },
    {
      title: '说明',
      dataIndex: 'description',
      render: (v: string | null, c) => (
        <span className="text-[12.5px] text-ink-2 leading-[1.6]">
          {v || CONFIG_META[c.config_key]?.impact || '—'}
        </span>
      ),
    },
    {
      title: '最后更新',
      dataIndex: 'updated_at',
      width: 164,
      render: (v: number) => (
        <span className="num text-ink-3 text-[12.5px]">{formatDateTime(v)}</span>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 88,
      align: 'center',
      render: (_: unknown, c) => (
        <Button type="link" size="small" onClick={() => openEdit(c)}>
          修改
        </Button>
      ),
    },
  ]

  const logColumns: ColumnsType<OperationLog> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 164,
      render: (v: number) => <span className="num text-[12.5px] text-ink-2">{formatDateTime(v)}</span>,
    },
    {
      title: '操作',
      dataIndex: 'action',
      width: 130,
      render: (v: string) => <Tag tone="muted">{v}</Tag>,
    },
    {
      title: '详情',
      dataIndex: 'detail',
      render: (v: string | null) => (
        <span className="text-[12.5px] text-ink-2 leading-[1.6]">{v || '—'}</span>
      ),
    },
    {
      title: '来源 IP',
      dataIndex: 'ip',
      width: 140,
      render: (v: string | null) => <span className="num text-[12px] text-ink-3">{v || '—'}</span>,
    },
  ]

  const meta = editing ? CONFIG_META[editing.config_key] : undefined

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="m-0 text-[22px] font-semibold text-ink">系统配置</h1>
        <p className="m-0 mt-1.5 text-[13.5px] text-ink-2 leading-[1.7]">
          调整系统的运行参数。<b className="text-ink">配置项逐项保存</b>，
          修改后立即对新发起的请求生效，不影响已产生的数据。
        </p>
      </header>

      <Alert tone="warn" title="修改前请注意">
        这些参数会直接影响所有用户的使用体验与系统资源占用。
        调整前请确认理解各项的作用，并建议在低峰时段进行。
      </Alert>

      {err && (
        <Alert
          tone="danger"
          title="配置加载失败"
          action={
            <Button size="small" onClick={() => void load()}>
              重试
            </Button>
          }
        >
          {err}
        </Alert>
      )}

      <Card title="运行参数" padding="none">
        {loading ? (
          <PageSkeleton variant="table" rows={5} showHeader={false} />
        ) : items.length === 0 ? (
          <EmptyState
            compact
            title="没有可配置的参数"
            description="系统尚未初始化配置项，通常说明数据库未完成种子数据写入。"
          />
        ) : (
          <Table<ConfigItem>
            rowKey="config_key"
            size="middle"
            columns={columns}
            dataSource={items}
            pagination={false}
          />
        )}
      </Card>

      {/* ── 操作日志（默认收起）──────────────────────────── */}
      <Collapse
        bordered={false}
        style={{ background: 'transparent' }}
        items={[
          {
            key: 'logs',
            label: (
              <span className="text-[15px] font-semibold text-ink">
                操作日志
                <span className="ml-2 text-[12.5px] font-normal text-ink-3">
                  记录登录、删除、配置变更等管理动作
                </span>
              </span>
            ),
            children: (
              <div>
                {logLoading ? (
                  <PageSkeleton variant="table" rows={4} showHeader={false} />
                ) : logs.length === 0 ? (
                  <EmptyState compact title="暂无操作日志" description="系统尚未记录到任何操作。" />
                ) : (
                  <Table<OperationLog>
                    rowKey="id"
                    size="small"
                    columns={logColumns}
                    dataSource={logs}
                    pagination={false}
                  />
                )}
                {logTotal > ADMIN_PAGE_SIZE && (
                  <div className="mt-3 flex justify-end">
                    <Pagination
                      size="small"
                      current={logPage}
                      pageSize={ADMIN_PAGE_SIZE}
                      total={logTotal}
                      showTotal={(t) => `共 ${formatNumber(t)} 条`}
                      onChange={(p) => {
                        setLogPage(p)
                        void loadLogs(p)
                      }}
                    />
                  </div>
                )}
              </div>
            ),
            // 首次展开时懒加载日志
            forceRender: false,
          },
        ]}
        onChange={(keys) => {
          if (Array.isArray(keys) && keys.includes('logs') && logs.length === 0) {
            void loadLogs(logPage)
          }
        }}
      />

      {/* ── 编辑弹窗（单点更新）──────────────────────────── */}
      <Modal
        open={editing !== null}
        onCancel={() => setEditing(null)}
        onOk={() => void submitEdit()}
        confirmLoading={saving}
        title={meta ? `修改「${meta.label}」` : '修改配置'}
        okText="保存"
        cancelText="取消"
        width={440}
        styles={{ content: { borderRadius: 'var(--radius-lg)' } }}
      >
        {fieldErr && (
          <Alert tone="danger" className="mb-4">
            {fieldErr}
          </Alert>
        )}

        <label className="block text-[13px] text-ink-2 mb-1.5" htmlFor="cfg-input">
          新的配置值
          {meta?.unit && <span className="text-ink-3">（单位：{meta.unit}）</span>}
        </label>
        <Input
          id="cfg-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onPressEnter={() => void submitEdit()}
          autoFocus
          status={fieldErr ? 'error' : undefined}
          placeholder={
            meta?.min !== undefined && meta?.max !== undefined
              ? `取值范围 ${meta.min} – ${meta.max}`
              : '请输入新的值'
          }
        />

        {meta && (
          <p className="m-0 mt-2 text-[12px] text-ink-3 leading-[1.6]">
            取值范围 {meta.min ?? '不限'} – {meta.max ?? '不限'}
            {meta.integer ? '（整数）' : ''}
          </p>
        )}

        {meta && (
          <Alert tone="info" className="mt-4">
            {meta.impact}
          </Alert>
        )}
      </Modal>
    </div>
  )
}
