/**
 * 页面 11 · 记录管理 `/admin/records`（视图 `adminRecords`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.11
 *
 * 需求锚点：FR-USER-08、BR-HISTORY-01、BR-HISTORY-03、BR-USER-10、BR-USER-17、NFR-SEC-03
 *
 * 布局骨架：
 *   ① 标题 + 全站统计（StatCard 行）
 *   ② 筛选条（用户 / 物种 / 时间 / 关键词）
 *   ③ **跨用户**记录表格（含归属用户列，这是与用户侧历史列表的关键差异）
 *   ④ 分页
 *
 * 【端点】`GET /api/admin/records` + `DELETE /api/admin/records/{id}`
 * 跨用户视图的 `user_id` 为**可选过滤器**（不传 = 全部用户）。
 * ────────────────────────────────────────────────────────────────
 */

import { useCallback, useEffect, useState } from 'react'
import { Button, Input, Select, DatePicker, Table, Popconfirm, Pagination } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import * as recordsApi from '@/api/records'
import * as configApi from '@/api/config'
import * as usersApi from '@/api/users'
import { resolveAssetUrl } from '@/api/images'
import { isApiError } from '@/api/client'
import { useSpeciesStore } from '@/stores/speciesStore'
import { useUiStore } from '@/stores/uiStore'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import { ADMIN_PAGE_SIZE } from '@/constants/limits'
import { RECORD_STATUS_META, type RecordStatus } from '@/constants/enums'
import type { AdminStats, RecordItem, User } from '@/api/types'
import Card from '@/components/base/Card'
import Tag from '@/components/base/Tag'
import Alert from '@/components/feedback/Alert'
import EmptyState from '@/components/data/EmptyState'
import PageSkeleton from '@/components/feedback/PageSkeleton'
import { formatConfidence, formatDateTime, formatDuration, formatNumber } from '@/utils/format'

export default function AdminRecords() {
  const { isMobile } = useBreakpoint()
  const speciesList = useSpeciesStore((s) => s.list)()
  const ensureSpecies = useSpeciesStore((s) => s.ensureLoaded)
  const toastOk = useUiStore((s) => s.toast)
  const toastErr = useUiStore((s) => s.toast)

  const [items, setItems] = useState<RecordItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const [userFilter, setUserFilter] = useState<number | undefined>()
  const [classIndex, setClassIndex] = useState<number | undefined>()
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [keyword, setKeyword] = useState('')

  const [userOptions, setUserOptions] = useState<User[]>([])
  const [stats, setStats] = useState<AdminStats | null>(null)

  useEffect(() => {
    void ensureSpecies()
  }, [ensureSpecies])

  /* 用户下拉与统计（加载失败静默降级，不阻断主表格） */
  useEffect(() => {
    usersApi
      .listUsers({ page: 1, page_size: 100 })
      .then((out) => setUserOptions(out.items))
      .catch(() => setUserOptions([]))
    configApi
      .getStats()
      .then(setStats)
      .catch(() => setStats(null))
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const out = await recordsApi.adminListRecords({
        page,
        page_size: ADMIN_PAGE_SIZE,
        user_id: userFilter,
        class_index: classIndex,
        keyword: keyword.trim() || undefined,
        start_ts: range?.[0] ? range[0].startOf('day').unix() : undefined,
        end_ts: range?.[1] ? range[1].endOf('day').unix() : undefined,
      })
      setItems(out.items)
      setTotal(out.total)
    } catch (e) {
      setErr(isApiError(e) ? e.message : '记录加载失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [page, userFilter, classIndex, keyword, range])

  useEffect(() => {
    void load()
  }, [load])

  const remove = async (r: RecordItem) => {
    try {
      await recordsApi.adminDeleteRecord(r.id)
      toastOk('记录已删除')
      void load()
    } catch (e) {
      toastErr(isApiError(e) ? e.message : '删除失败，请稍后重试', 'danger')
    }
  }

  const hasFilter =
    userFilter !== undefined || classIndex !== undefined || Boolean(range) || keyword.trim() !== ''

  const resetFilters = () => {
    setUserFilter(undefined)
    setClassIndex(undefined)
    setRange(null)
    setKeyword('')
    setPage(1)
  }

  /** 归属用户查表（后端记录列表不含用户名，需前端映射） */
  const userLabel = (r: RecordItem): string => {
    const uid = (r as RecordItem & { user_id?: number | null }).user_id
    if (uid == null) return '—'
    const u = userOptions.find((x) => x.id === uid)
    return u ? u.username : `#${uid}`
  }

  const columns: ColumnsType<RecordItem> = [
    {
      title: '原图',
      dataIndex: 'thumb_url',
      width: 72,
      align: 'center',
      render: (_: unknown, r) => {
        const url = resolveAssetUrl(r.thumb_url)
        return url ? (
          <img
            src={url}
            alt={r.cn_name}
            loading="lazy"
            className="object-cover border border-line mx-auto"
            style={{ width: 40, height: 40, borderRadius: 'var(--radius)' }}
          />
        ) : (
          <span className="text-[11.5px] text-ink-3">已过期</span>
        )
      },
    },
    {
      title: '物种',
      dataIndex: 'cn_name',
      render: (_: unknown, r) => (
        <div className="min-w-0">
          <p className="m-0 text-[13.5px] font-medium text-ink truncate">{r.cn_name}</p>
          <p className="m-0 text-[11.5px] italic text-ink-3 truncate">{r.latin_name}</p>
        </div>
      ),
    },
    {
      title: '归属用户',
      key: 'owner',
      width: 128,
      render: (_: unknown, r) => (
        <span className="text-[12.5px] text-ink-2 num truncate">{userLabel(r)}</span>
      ),
    },
    {
      title: '置信度',
      dataIndex: 'confidence',
      width: 100,
      align: 'right',
      render: (_: unknown, r) => (
        <span
          className="num"
          style={{ color: r.is_low_confidence ? 'var(--warn)' : 'var(--metric-deep)' }}
        >
          {formatConfidence(r.confidence)}
        </span>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 88,
      align: 'right',
      render: (v: number) => <span className="num text-ink-2">{formatDuration(v)}</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 92,
      align: 'center',
      render: (v: RecordStatus) => {
        const m = RECORD_STATUS_META[v]
        return <Tag tone={m.tone}>{m.label}</Tag>
      },
    },
    {
      title: '识别时间',
      dataIndex: 'created_at',
      width: 164,
      render: (v: number) => (
        <span className="num text-ink-2 text-[12.5px]">{formatDateTime(v)}</span>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 88,
      align: 'center',
      render: (_: unknown, r) => (
        <Popconfirm
          title="删除这条记录？"
          description="该记录将从所属用户的历史中一并移除，此操作不可撤销。"
          okText="删除"
          cancelText="取消"
          okButtonProps={{ danger: true }}
          onConfirm={() => void remove(r)}
        >
          <Button type="link" size="small" danger>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="m-0 text-[22px] font-semibold text-ink">记录管理</h1>
        <p className="m-0 mt-1.5 text-[13.5px] text-ink-2 leading-[1.7]">
          查看并管理全部用户的识别记录。共 <b className="num text-ink">{total}</b> 条
          {hasFilter && <span className="text-ink-3">（当前为筛选结果）</span>}
        </p>
      </header>

      {/* ── 统计卡（有数据才渲染）──────────────────────────── */}
      {stats && (
        <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
          <StatCard label="账号总数" value={formatNumber(stats.total_users)} sub={`其中启用 ${stats.active_users}`} />
          <StatCard label="识别记录" value={formatNumber(stats.total_records)} sub={`今日新增 ${stats.records_today}`} />
          <StatCard label="上传图片" value={formatNumber(stats.total_uploads)} />
          <StatCard
            label="平均耗时"
            value={formatDuration(stats.avg_duration_ms)}
            sub="全部识别记录"
          />
        </div>
      )}

      {/* ── 筛选条 ────────────────────────────────────────── */}
      <Card padding="sm">
        <div className="flex flex-wrap gap-3 items-center">
          <Select
            allowClear
            showSearch
            placeholder="按用户筛选"
            style={{ width: 180 }}
            value={userFilter}
            onChange={(v) => {
              setUserFilter(v)
              setPage(1)
            }}
            optionFilterProp="label"
            options={userOptions.map((u) => ({
              value: u.id,
              label: `${u.username}${u.nickname ? `（${u.nickname}）` : ''}`,
            }))}
          />

          <Select
            allowClear
            showSearch
            placeholder="按物种筛选"
            style={{ width: 200 }}
            value={classIndex}
            onChange={(v) => {
              setClassIndex(v)
              setPage(1)
            }}
            optionFilterProp="label"
            options={speciesList.map((s) => ({
              value: s.class_index,
              label: `${s.cn_name}（${s.latin_name}）`,
            }))}
          />

          <DatePicker.RangePicker
            value={range as never}
            onChange={(v) => {
              setRange(v as [Dayjs | null, Dayjs | null] | null)
              setPage(1)
            }}
            placeholder={['开始日期', '结束日期']}
            style={{ width: 250 }}
          />

          <Input.Search
            allowClear
            placeholder="搜索物种名称"
            style={{ width: 180 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onSearch={() => setPage(1)}
            maxLength={50}
          />

          {hasFilter && (
            <Button type="link" size="small" onClick={resetFilters}>
              清除全部筛选
            </Button>
          )}
        </div>
      </Card>

      {err && (
        <Alert
          tone="danger"
          title="记录加载失败"
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
            title={hasFilter ? '没有符合条件的记录' : '系统内还没有识别记录'}
            description={
              hasFilter
                ? '当前筛选条件下没有找到记录，试试放宽时间范围或清除部分条件。'
                : '当有用户完成识别后，记录会出现在这里。'
            }
            action={hasFilter ? <Button onClick={resetFilters}>清除筛选条件</Button> : undefined}
          />
        </Card>
      ) : isMobile ? (
        <ul className="m-0 p-0 list-none flex flex-col gap-2.5">
          {items.map((r) => (
            <li key={r.id} className="rounded-lg border border-line bg-surface p-3.5">
              <div className="flex items-start gap-3">
                <MobileThumb url={resolveAssetUrl(r.thumb_url)} alt={r.cn_name} />
                <div className="flex-1 min-w-0">
                  <p className="m-0 text-[14px] font-medium text-ink truncate">{r.cn_name}</p>
                  <p className="m-0 text-[11.5px] italic text-ink-3 truncate">{r.latin_name}</p>
                  <p className="m-0 mt-1 text-[12px] text-ink-2 num truncate">
                    归属：{userLabel(r)}
                  </p>
                  <div className="mt-1.5 flex items-center gap-2 flex-wrap">
                    <span className="text-[12.5px] num text-ink-2">{formatConfidence(r.confidence)}</span>
                    <Tag tone={RECORD_STATUS_META[r.status].tone}>{RECORD_STATUS_META[r.status].label}</Tag>
                  </div>
                  <p className="m-0 mt-1 text-[11.5px] text-ink-3 num">{formatDateTime(r.created_at)}</p>
                </div>
              </div>
              <div className="mt-2.5 pt-2.5 border-t border-line">
                <Popconfirm
                  title="删除这条记录？"
                  description="该记录将从所属用户的历史中一并移除。"
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => void remove(r)}
                >
                  <Button size="small" danger>
                    删除记录
                  </Button>
                </Popconfirm>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <Card padding="none">
          <Table<RecordItem>
            rowKey="id"
            size="middle"
            columns={columns}
            dataSource={items}
            pagination={false}
            scroll={{ x: 980 }}
          />
        </Card>
      )}

      {total > ADMIN_PAGE_SIZE && (
        <div className="flex justify-end">
          <Pagination
            current={page}
            pageSize={ADMIN_PAGE_SIZE}
            total={total}
            showSizeChanger={false}
            pageSizeOptions={[String(ADMIN_PAGE_SIZE)]}
            showTotal={(t) => `共 ${t} 条`}
            onChange={setPage}
          />
        </div>
      )}

      {!loading && items.length > 0 && (
        <Alert tone="warn" title="删除操作影响用户数据">
          在此删除的记录会同时从对应用户的历史列表中移除，且不可恢复。
          删除前请确认该记录确实需要清理。
        </Alert>
      )}
    </div>
  )
}

/* ── 局部组件 ────────────────────────────────────────────────── */

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="m-0 text-[12.5px] text-ink-3">{label}</p>
      <p className="m-0 mt-1 text-[22px] font-semibold text-ink num leading-tight">{value}</p>
      {sub && <p className="m-0 mt-0.5 text-[11.5px] text-ink-3">{sub}</p>}
    </div>
  )
}

function MobileThumb({ url, alt }: { url: string | null; alt: string }) {
  if (!url) {
    return (
      <div
        className="shrink-0 border border-line flex items-center justify-center text-[10px] text-ink-3"
        style={{ width: 52, height: 52, borderRadius: 'var(--radius)', background: 'var(--surface-3)' }}
      >
        无图
      </div>
    )
  }
  return (
    <img
      src={url}
      alt={alt}
      loading="lazy"
      className="shrink-0 object-cover border border-line"
      style={{ width: 52, height: 52, borderRadius: 'var(--radius)' }}
    />
  )
}

void dayjs
