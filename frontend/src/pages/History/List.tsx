/**
 * 页面 6 · 历史记录 `/history`（视图 `history`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.6
 *
 * 需求锚点：FR-HISTORY-01～06、BR-HISTORY-01～10、BR-USER-10
 *
 * 布局骨架：
 *   ① 标题 + 统计摘要
 *   ② 筛选条（物种 / 时间范围 / 关键词）+ 导出按钮
 *   ③ 记录表格（桌面）/ 卡片列表（移动，§8.1.3 须卡片化，禁横向滚动）
 *   ④ 分页
 *   ⑤ 批量操作条（选中 ≥1 时浮出）
 *
 * 状态与空态：
 *   无记录 → EmptyState 三段式
 *   筛选无结果 → 区分「本来就没记录」与「筛选条件过窄」两种文案
 * ────────────────────────────────────────────────────────────────
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Select, DatePicker, Table, Checkbox, Pagination, Popconfirm } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import * as recordsApi from '@/api/records'
import { imageThumbUrl, resolveAssetUrl } from '@/api/images'
import { isApiError } from '@/api/client'
import { useSpeciesStore } from '@/stores/speciesStore'
import { useUiStore } from '@/stores/uiStore'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import { PATHS } from '@/routes/paths'
import { PAGE_SIZE_DEFAULT } from '@/constants/limits'
import { RECORD_STATUS_META, type RecordStatus } from '@/constants/enums'
import type { RecordItem } from '@/api/types'
import Card from '@/components/base/Card'
import Tag from '@/components/base/Tag'
import Alert from '@/components/feedback/Alert'
import EmptyState from '@/components/data/EmptyState'
import PageSkeleton from '@/components/feedback/PageSkeleton'
import { formatConfidence, formatDateTime, formatDuration } from '@/utils/format'

export default function HistoryList() {
  const navigate = useNavigate()
  const { isMobile } = useBreakpoint()
  const speciesList = useSpeciesStore((s) => s.list)()
  const ensureSpecies = useSpeciesStore((s) => s.ensureLoaded)
  const toastOk = useUiStore((s) => s.toast)
  const toastErr = useUiStore((s) => s.toast)

  const [items, setItems] = useState<RecordItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(PAGE_SIZE_DEFAULT)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  const [classIndex, setClassIndex] = useState<number | undefined>()
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [keyword, setKeyword] = useState('')
  const [selected, setSelected] = useState<string[]>([])

  useEffect(() => {
    void ensureSpecies()
  }, [ensureSpecies])

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      const out = await recordsApi.listHistory({
        page,
        page_size: pageSize,
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
  }, [page, pageSize, classIndex, keyword, range])

  useEffect(() => {
    void load()
  }, [load])

  const hasFilter = classIndex !== undefined || Boolean(range) || keyword.trim() !== ''

  /* ── 删除 ──────────────────────────────────────────────────── */

  const deleteOne = async (id: string) => {
    try {
      await recordsApi.deleteOneRecord(id)
      toastOk('记录已删除')
      setSelected((s) => s.filter((x) => x !== id))
      void load()
    } catch (e) {
      toastErr(isApiError(e) ? e.message : '删除失败，请稍后重试', 'danger')
    }
  }

  const deleteSelected = async () => {
    try {
      const out = await recordsApi.deleteRecords(selected)
      toastOk(`已删除 ${out.deleted} 条记录`)
      setSelected([])
      void load()
    } catch (e) {
      toastErr(isApiError(e) ? e.message : '删除失败，请稍后重试', 'danger')
    }
  }

  const exportCsv = async () => {
    try {
      const blob = await recordsApi.exportHistoryCsv({
        class_index: classIndex,
        keyword: keyword.trim() || undefined,
        start_ts: range?.[0] ? range[0].startOf('day').unix() : undefined,
        end_ts: range?.[1] ? range[1].endOf('day').unix() : undefined,
      })
      recordsApi.downloadBlob(blob, `海瞳鱼鉴-识别记录-${dayjs().format('YYYYMMDD-HHmm')}.csv`)
      toastOk('已开始下载')
    } catch (e) {
      toastErr(isApiError(e) ? e.message : '导出失败，请稍后重试', 'danger')
    }
  }

  const resetFilters = () => {
    setClassIndex(undefined)
    setRange(null)
    setKeyword('')
    setPage(1)
  }

  /* ── 表格列（桌面）─────────────────────────────────────────── */

  const columns: ColumnsType<RecordItem> = useMemo(
    () => [
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
              style={{ width: 44, height: 44, borderRadius: 'var(--radius)' }}
            />
          ) : (
            <div
              className="mx-auto flex items-center justify-center text-[11px] text-ink-3 border border-line"
              style={{ width: 44, height: 44, borderRadius: 'var(--radius)', background: 'var(--surface-3)' }}
            >
              已过期
            </div>
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
        title: '置信度',
        dataIndex: 'confidence',
        width: 108,
        align: 'right',
        render: (_: unknown, r) => (
          <span className="num" style={{ color: r.is_low_confidence ? 'var(--warn)' : 'var(--metric-deep)' }}>
            {formatConfidence(r.confidence)}
          </span>
        ),
      },
      {
        title: '耗时',
        dataIndex: 'duration_ms',
        width: 92,
        align: 'right',
        render: (v: number) => <span className="num text-ink-2">{formatDuration(v)}</span>,
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 96,
        align: 'center',
        render: (v: RecordStatus) => {
          const m = RECORD_STATUS_META[v]
          return <Tag tone={m.tone}>{m.label}</Tag>
        },
      },
      {
        title: '识别时间',
        dataIndex: 'created_at',
        width: 168,
        render: (v: number) => <span className="num text-ink-2 text-[12.5px]">{formatDateTime(v)}</span>,
      },
      {
        title: '操作',
        key: 'action',
        width: 116,
        align: 'center',
        render: (_: unknown, r) => (
          <div className="flex gap-1 justify-center">
            <Button type="link" size="small" onClick={() => navigate(PATHS.historyDetail(r.id))}>
              查看
            </Button>
            <Popconfirm
              title="删除这条记录？"
              description="删除后该条识别结果将不再显示，此操作不可撤销。"
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => void deleteOne(r.id)}
            >
              <Button type="link" size="small" danger>
                删除
              </Button>
            </Popconfirm>
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [navigate],
  )

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-start gap-3 justify-between">
        <div>
          <h1 className="m-0 text-[22px] font-semibold text-ink">历史记录</h1>
          <p className="m-0 mt-1.5 text-[13.5px] text-ink-2">
            共 <b className="num text-ink">{total}</b> 条识别记录
            {hasFilter && <span className="text-ink-3">（当前为筛选结果）</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <Link_CompareButton disabled={total < 2} />
          <Button onClick={() => void exportCsv()} disabled={total === 0}>
            导出 CSV
          </Button>
        </div>
      </header>

      {/* ── 筛选条 ────────────────────────────────────────── */}
      <Card padding="sm">
        <div className="flex flex-wrap gap-3 items-center">
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
            style={{ width: 200 }}
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

          <div className="flex-1" />

          {selected.length > 0 && (
            <div className="flex items-center gap-2.5">
              <span className="text-[12.5px] text-ink-2">
                已选 <b className="num">{selected.length}</b> 条
              </span>
              <Popconfirm
                title={`删除选中的 ${selected.length} 条记录？`}
                description="删除后这些识别结果将不再显示，此操作不可撤销。"
                okText="删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={() => void deleteSelected()}
              >
                <Button danger size="small">
                  批量删除
                </Button>
              </Popconfirm>
            </div>
          )}
        </div>
      </Card>

      {/* ── 错误 ──────────────────────────────────────────── */}
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

      {/* ── 内容 ──────────────────────────────────────────── */}
      {loading ? (
        <PageSkeleton variant="table" rows={6} showHeader={false} />
      ) : items.length === 0 ? (
        hasFilter ? (
          <Card>
            <EmptyState
              title="没有符合条件的记录"
              description="当前筛选条件下没有找到识别记录。可能是时间范围过窄，或关键词与任何物种名称都不匹配。"
              action={<Button onClick={resetFilters}>清除筛选条件</Button>}
            />
          </Card>
        ) : (
          <Card>
            <EmptyState
              title="还没有识别记录"
              description="每次成功识别后，结果会自动保存到这里，方便你回看物种信息与当时的判定置信度。"
              action={<Link_RecognizeButton />}
              hint="游客试用不保存记录，登录后才会归档"
            />
          </Card>
        )
      ) : isMobile ? (
        /* ── 移动端：卡片化（禁横向滚动，D9 §8.1.3）────────── */
        <ul className="m-0 p-0 list-none flex flex-col gap-2.5">
          {items.map((r) => (
            <li key={r.id} className="rounded-lg border border-line bg-surface p-3.5">
              <div className="flex gap-3">
                <Checkbox
                  checked={selected.includes(r.id)}
                  onChange={(e) =>
                    setSelected((s) => (e.target.checked ? [...s, r.id] : s.filter((x) => x !== r.id)))
                  }
                  aria-label={`选择 ${r.cn_name} 这条记录`}
                />
                <MobileThumb url={resolveAssetUrl(r.thumb_url)} alt={r.cn_name} />
                <div className="flex-1 min-w-0">
                  <p className="m-0 text-[14px] font-medium text-ink truncate">{r.cn_name}</p>
                  <p className="m-0 text-[11.5px] italic text-ink-3 truncate">{r.latin_name}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    <span className="text-[12.5px] num text-ink-2">
                      {formatConfidence(r.confidence)}
                    </span>
                    <Tag tone={RECORD_STATUS_META[r.status].tone}>{RECORD_STATUS_META[r.status].label}</Tag>
                  </div>
                  <p className="m-0 mt-1 text-[11.5px] text-ink-3 num">{formatDateTime(r.created_at)}</p>
                </div>
              </div>
              <div className="mt-2.5 pt-2.5 border-t border-line flex gap-2">
                <Button size="small" onClick={() => navigate(PATHS.historyDetail(r.id))}>
                  查看详情
                </Button>
                <Popconfirm
                  title="删除这条记录？"
                  description="删除后不可撤销。"
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => void deleteOne(r.id)}
                >
                  <Button size="small" danger>
                    删除
                  </Button>
                </Popconfirm>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        /* ── 桌面：表格 ────────────────────────────────────── */
        <Card padding="none">
          <Table<RecordItem>
            rowKey="id"
            size="middle"
            columns={columns}
            dataSource={items}
            pagination={false}
            scroll={{ x: 900 }}
            rowSelection={{
              selectedRowKeys: selected,
              onChange: (keys) => setSelected(keys as string[]),
              columnWidth: 44,
            }}
          />
        </Card>
      )}

      {/* ── 分页 ──────────────────────────────────────────── */}
      {total > pageSize && (
        <div className="flex justify-end">
          <Pagination
            current={page}
            pageSize={pageSize}
            total={total}
            showSizeChanger
            pageSizeOptions={['10', '20', '50']}
            showTotal={(t) => `共 ${t} 条`}
            onChange={(p, ps) => {
              setPage(p)
              setPageSize(ps)
            }}
          />
        </div>
      )}

      {/* 移动端底部批量操作栏（§8.2.3） */}
      {isMobile && selected.length > 0 && (
        <div
          className="fixed left-0 right-0 bottom-0 z-topbar flex items-center gap-3 px-4 py-3 border-t border-line"
          style={{ background: 'var(--ink)' }}
        >
          <span className="text-[13px] text-white">已选 {selected.length} 条</span>
          <div className="flex-1" />
          <Button size="small" onClick={() => setSelected([])}>
            取消
          </Button>
          <Popconfirm
            title={`删除选中的 ${selected.length} 条记录？`}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => void deleteSelected()}
          >
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </div>
      )}
    </div>
  )
}

/* ── 局部组件 ────────────────────────────────────────────────── */

import { Link } from 'react-router-dom'

function Link_CompareButton({ disabled }: { disabled: boolean }) {
  return (
    <Link to={PATHS.historyCompare} className="no-underline">
      <Button disabled={disabled} title={disabled ? '至少需要 2 条记录才能对比' : undefined}>
        对比分析
      </Button>
    </Link>
  )
}

function Link_RecognizeButton() {
  return (
    <Link to={PATHS.recognize} className="no-underline">
      <Button type="primary">去识别一张</Button>
    </Link>
  )
}

function MobileThumb({ url, alt }: { url: string | null; alt: string }) {
  if (!url) {
    return (
      <div
        className="shrink-0 flex items-center justify-center text-[10.5px] text-ink-3 border border-line text-center leading-tight"
        style={{ width: 56, height: 56, borderRadius: 'var(--radius)', background: 'var(--surface-3)' }}
      >
        原图
        <br />
        已过期
      </div>
    )
  }
  return (
    <img
      src={url}
      alt={alt}
      loading="lazy"
      className="shrink-0 object-cover border border-line"
      style={{ width: 56, height: 56, borderRadius: 'var(--radius)' }}
    />
  )
}

/** 供 thumb_url 直拼的辅助（避免误用）—— 保留 imageThumbUrl 以维持 API 完整性 */
void imageThumbUrl
