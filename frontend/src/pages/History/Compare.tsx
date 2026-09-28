/**
 * 页面 8 · 对比视图 `/history/compare`（视图 `compare`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.8
 *
 * 需求锚点：FR-HISTORY-04、BR-HISTORY-09、BR-RESULT-08
 *
 * 布局骨架：
 *   ① 标题 + 说明
 *   ② 记录选择器（从历史记录中勾选 2～4 条）
 *   ③ 并排对比表（每列一条记录）
 *   ④ 置信度对比条形图（共用同一 Y 轴尺度，便于横向比较）
 *
 * 【⚠ 实现约束】后端**不存在** `POST /api/records/compare` 端点
 * （该路径见于 D9 §10.4.4，属文档自身臆造）。本页改为：
 *   使用 `GET /api/history` 拉取候选记录 + 逐条 `GET /api/history/{id}`
 *   取候选，在前端完成对比组装。
 *   已登记于 `docs/海瞳鱼鉴-接口契约偏离诊断.md`（EC-12）。
 * ────────────────────────────────────────────────────────────────
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button, Checkbox, Pagination } from 'antd'
import * as recordsApi from '@/api/records'
import { imageThumbUrl, resolveAssetUrl } from '@/api/images'
import { isApiError } from '@/api/client'
import { useUiStore } from '@/stores/uiStore'
import { COMPARE_MAX, COMPARE_MIN, PAGE_SIZE_DEFAULT } from '@/constants/limits'
import { PATHS } from '@/routes/paths'
import type { Candidate, RecordDetailOut, RecordItem } from '@/api/types'
import Card from '@/components/base/Card'
import Alert from '@/components/feedback/Alert'
import EmptyState from '@/components/data/EmptyState'
import PageSkeleton from '@/components/feedback/PageSkeleton'
import { formatConfidence, formatDateTime, formatDuration } from '@/utils/format'

export default function Compare() {
  const [params, setParams] = useSearchParams()
  const toastErr = useUiStore((s) => s.toast)

  const [items, setItems] = useState<RecordItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [listLoading, setListLoading] = useState(true)

  const [picked, setPicked] = useState<string[]>(() => {
    const raw = params.get('ids')
    return raw ? raw.split(',').filter(Boolean).slice(0, COMPARE_MAX) : []
  })
  const [details, setDetails] = useState<Record<string, RecordDetailOut>>({})
  const [detailLoading, setDetailLoading] = useState(false)

  /* ── 拉取可选记录 ────────────────────────────────────────── */
  const loadList = useCallback(async () => {
    setListLoading(true)
    try {
      const out = await recordsApi.listHistory({ page, page_size: PAGE_SIZE_DEFAULT })
      setItems(out.items)
      setTotal(out.total)
    } catch (e) {
      toastErr(isApiError(e) ? e.message : '记录加载失败，请稍后重试', 'danger')
    } finally {
      setListLoading(false)
    }
  }, [page, toastErr])

  useEffect(() => {
    void loadList()
  }, [loadList])

  /* ── 同步 URL（可分享的对比链接）────────────────────────── */
  useEffect(() => {
    const next = new URLSearchParams(params)
    if (picked.length > 0) next.set('ids', picked.join(','))
    else next.delete('ids')
    setParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picked])

  /* ── 拉取所选记录的详情（逐条并发）──────────────────────── */
  useEffect(() => {
    const missing = picked.filter((id) => !details[id])
    if (missing.length === 0) return
    let cancelled = false
    setDetailLoading(true)
    Promise.all(
      missing.map((id) =>
        recordsApi
          .getHistoryDetail(id)
          .then((d) => [id, d] as const)
          .catch(() => null),
      ),
    )
      .then((rows) => {
        if (cancelled) return
        setDetails((prev) => {
          const next = { ...prev }
          for (const r of rows) if (r) next[r[0]] = r[1]
          return next
        })
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [picked, details])

  const toggle = (id: string) => {
    setPicked((s) => {
      if (s.includes(id)) return s.filter((x) => x !== id)
      if (s.length >= COMPARE_MAX) return s
      return [...s, id]
    })
    // 取消选择时清理已缓存的详情
    setDetails((prev) => {
      if (!prev[id]) return prev
      const next = { ...prev }
      delete next[id]
      return next
    })
  }

  const columns = useMemo(
    () => picked.map((id) => details[id]).filter((d): d is RecordDetailOut => Boolean(d)),
    [picked, details],
  )

  const ready = columns.length >= COMPARE_MIN

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="m-0 text-[22px] font-semibold text-ink">对比分析</h1>
        <p className="m-0 mt-1.5 text-[13.5px] text-ink-2 leading-[1.7]">
          勾选 {COMPARE_MIN}～{COMPARE_MAX} 条识别记录，并排查看物种判定、
          置信度与 Top-5 候选分布，便于判断模型在不同样本上的稳定程度。
        </p>
      </header>

      {/* ── ② 记录选择器 ──────────────────────────────────── */}
      <Card
        title={`选择要对比的记录（已选 ${picked.length} / ${COMPARE_MAX}）`}
        description={`至少选择 ${COMPARE_MIN} 条才能开始对比。`}
        extra={
          picked.length > 0 ? (
            <Button size="small" onClick={() => setPicked([])}>
              清空选择
            </Button>
          ) : undefined
        }
      >
        {listLoading ? (
          <PageSkeleton variant="list" rows={3} showHeader={false} />
        ) : items.length === 0 ? (
          <EmptyState
            compact
            title="还没有可对比的记录"
            description="需要先有识别历史才能生成对比视图。"
            action={<Link_Recognize />}
          />
        ) : (
          <>
            <ul className="m-0 p-0 list-none grid gap-2.5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((r) => {
                const on = picked.includes(r.id)
                const full = !on && picked.length >= COMPARE_MAX
                return (
                  <li key={r.id}>
                    <label
                      className={[
                        'flex items-center gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors',
                        on ? 'border-brand bg-brand-50' : 'border-line bg-surface hover:border-line-strong',
                        full ? 'opacity-50 cursor-not-allowed' : '',
                      ].join(' ')}
                    >
                      <Checkbox
                        checked={on}
                        disabled={full}
                        onChange={() => toggle(r.id)}
                        aria-label={`选择 ${r.cn_name} 这条记录`}
                      />
                      <Thumb url={resolveAssetUrl(r.thumb_url)} alt={r.cn_name} />
                      <div className="flex-1 min-w-0">
                        <p className="m-0 text-[13.5px] font-medium text-ink truncate">{r.cn_name}</p>
                        <p className="m-0 mt-0.5 text-[11.5px] text-ink-3 num truncate">
                          {formatConfidence(r.confidence)} · {formatDateTime(r.created_at)}
                        </p>
                      </div>
                    </label>
                  </li>
                )
              })}
            </ul>

            {total > PAGE_SIZE_DEFAULT && (
              <div className="mt-3.5 flex justify-end">
                <Pagination
                  size="small"
                  current={page}
                  pageSize={PAGE_SIZE_DEFAULT}
                  total={total}
                  onChange={setPage}
                />
              </div>
            )}
          </>
        )}
      </Card>

      {/* ── ③ 对比区 ──────────────────────────────────────── */}
      {picked.length > 0 && picked.length < COMPARE_MIN && (
        <Alert tone="info">
          还需再选 {COMPARE_MIN - picked.length} 条记录才能生成对比。
        </Alert>
      )}

      {detailLoading && <PageSkeleton variant="card" rows={3} showHeader={false} />}

      {ready && !detailLoading && (
        <>
          {/* 并排对比表 */}
          <Card title="并排对比" padding="none">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[13px]">
                <thead>
                  <tr style={{ background: 'var(--surface-2)' }}>
                    <th className="text-left px-4 py-3 font-medium text-ink-2 border-b border-line whitespace-nowrap w-[120px]">
                      对比项
                    </th>
                    {columns.map((c) => (
                      <th
                        key={c.record.id}
                        className="text-left px-4 py-3 font-medium text-ink border-b border-line min-w-[180px]"
                      >
                        <span className="block truncate">{c.record.cn_name}</span>
                        <span className="block text-[11.5px] italic text-ink-3 font-normal truncate">
                          {c.record.latin_name}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <Row label="置信度" cols={columns} render={(c) => (
                    <span className="num" style={{ color: c.record.is_low_confidence ? 'var(--warn)' : 'var(--metric-deep)', fontWeight: 600 }}>
                      {formatConfidence(c.record.confidence)}
                    </span>
                  )} />
                  <Row label="物种编号" cols={columns} render={(c) => <span className="num text-ink-2">#{c.record.class_index}</span>} />
                  <Row label="识别耗时" cols={columns} render={(c) => <span className="num text-ink-2">{formatDuration(c.record.duration_ms)}</span>} />
                  <Row label="识别时间" cols={columns} render={(c) => <span className="num text-ink-2">{formatDateTime(c.record.created_at)}</span>} />
                  <Row label="Top-5 候选" cols={columns} render={(c) => <TopList candidates={c.candidates} />} />
                  <Row
                    label="候选一致性"
                    cols={columns}
                    render={(c) => (
                      <AgreementBadge
                        candidates={c.candidates}
                        allColumns={columns}
                      />
                    )}
                  />
                </tbody>
              </table>
            </div>
          </Card>

          {/* 置信度对比条形图（统一尺度） */}
          <Card
            title="置信度横向对比"
            description="所有条形使用相同的满量程（0–100%），便于直接比较高度。"
          >
            <ConfidenceCompare columns={columns} />
          </Card>

          <Alert tone="info">
            对比结果反映的是模型在**不同图片**上的判定差异，不表示任何一条判定
            比另一条更「正确」。若两条记录指向同一物种但置信度相差较大，
            通常说明其中一张图片的拍摄条件更有利于模型判断。
          </Alert>
        </>
      )}

      {picked.length === 0 && items.length > 0 && (
        <Card>
          <EmptyState
            title="先选择要对比的记录"
            description={`在上方列表勾选 ${COMPARE_MIN}～${COMPARE_MAX} 条记录，这里会呈现并排对比结果。`}
          />
        </Card>
      )}
    </div>
  )
}

/* ── 局部组件 ────────────────────────────────────────────────── */

function Link_Recognize() {
  return (
    <Link to={PATHS.recognize} className="no-underline">
      <Button type="primary">去识别一张</Button>
    </Link>
  )
}

function Thumb({ url, alt }: { url: string | null; alt: string }) {
  if (!url) {
    return (
      <div
        className="shrink-0 border border-line flex items-center justify-center text-[10px] text-ink-3"
        style={{ width: 40, height: 40, borderRadius: 'var(--radius)', background: 'var(--surface-3)' }}
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
      style={{ width: 40, height: 40, borderRadius: 'var(--radius)' }}
    />
  )
}

function Row({
  label,
  cols,
  render,
}: {
  label: string
  cols: RecordDetailOut[]
  render: (c: RecordDetailOut) => React.ReactNode
}) {
  return (
    <tr className="border-b border-line last:border-b-0">
      <th
        scope="row"
        className="text-left px-4 py-3 font-normal text-ink-2 align-top whitespace-nowrap"
        style={{ background: 'var(--surface-2)' }}
      >
        {label}
      </th>
      {cols.map((c) => (
        <td key={c.record.id} className="px-4 py-3 align-top">
          {render(c)}
        </td>
      ))}
    </tr>
  )
}

function TopList({ candidates }: { candidates: Candidate[] }) {
  return (
    <ol className="m-0 p-0 pl-4 list-decimal flex flex-col gap-0.5">
      {candidates.map((c) => (
        <li key={c.class_index} className="text-[12.5px] text-ink-2">
          <span className="truncate">{c.cn_name}</span>{' '}
          <span className="num" style={{ color: 'var(--metric-deep)' }}>
            {formatConfidence(c.confidence)}
          </span>
        </li>
      ))}
    </ol>
  )
}

/** 候选一致性：本列首位是否出现在其他列的 Top-5 中 */
function AgreementBadge({
  candidates,
  allColumns,
}: {
  candidates: Candidate[]
  allColumns: RecordDetailOut[]
}) {
  const mine = candidates[0]?.class_index
  if (mine === undefined) return <span className="text-ink-3">—</span>

  const others = allColumns.filter((c) => c.candidates[0]?.class_index !== mine)
  if (others.length === 0) return <span className="text-ink-3">已与其余全部一致</span>

  const hits = others.filter((c) => c.candidates.some((x) => x.class_index === mine)).length
  const tone = hits === others.length ? 'var(--success)' : hits === 0 ? 'var(--danger)' : 'var(--warn)'

  return (
    <span style={{ color: tone }} className="text-[12.5px]">
      {hits} / {others.length} 条其他记录的 Top-5 含本物种
    </span>
  )
}

/** 置信度横向对比（统一满量程 0–100%） */
function ConfidenceCompare({ columns }: { columns: RecordDetailOut[] }) {
  return (
    <ul className="m-0 p-0 list-none flex flex-col gap-4">
      {columns.map((c) => {
        const pct = Math.max(1, c.record.confidence * 100)
        return (
          <li key={c.record.id}>
            <div className="flex items-baseline gap-2 mb-1.5">
              <span className="flex-1 min-w-0 truncate text-[13.5px] font-medium text-ink">
                {c.record.cn_name}
              </span>
              <span className="shrink-0 text-[12.5px] text-ink-3 num">
                {formatDateTime(c.record.created_at)}
              </span>
              <span className="shrink-0 text-[13px] num font-semibold" style={{ color: 'var(--primary-600)' }}>
                {formatConfidence(c.record.confidence)}
              </span>
            </div>
            <div
              className="w-full overflow-hidden"
              style={{ height: 10, background: 'var(--surface-3)', borderRadius: 5 }}
              role="img"
              aria-label={`${c.record.cn_name} 置信度 ${formatConfidence(c.record.confidence)}`}
            >
              <div
                style={{
                  width: `${pct}%`,
                  height: '100%',
                  background: c.record.is_low_confidence ? 'var(--warn)' : 'var(--primary)',
                  borderRadius: 5,
                  transition: 'width 450ms cubic-bezier(.4,0,.2,1)',
                }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

void imageThumbUrl
