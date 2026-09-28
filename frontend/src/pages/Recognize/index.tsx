/**
 * 页面 2 · 识别工作台 `/recognize`（视图 `recognize`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.2
 *
 * 需求锚点（36 条，本页是全站最密集的页面）：
 *   FR-UPLOAD-01～08、FR-RECOG-01～06、FR-RESULT-01～06、FR-USER-06、
 *   BR-UPLOAD-01～05/07/08、BR-RECOG-04/09、BR-RESULT-01～05/07
 *
 * 布局骨架（§5.2）：
 *   ① 页面标题 + 额度提示
 *   ② 上传区（DropZone）
 *   ③ 文件队列（缩略图卡 + 单张状态 + 移除）
 *   ④ 操作条（开始识别 / 清空）
 *   ⑤ 结果区（单张用 ResultHero + ProbBarChart；多张用结果列表）
 *
 * 状态与空态（§6.1 状态机）：idle → ready → uploading → recognizing
 *   → done / partial / failed；额度耗尽时中断并弹登录引导。
 * ────────────────────────────────────────────────────────────────
 */

import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from 'antd'
import { useRecognizeStore } from '@/stores/recognizeStore'
import { useAuthStore } from '@/stores/authStore'
import { useSpeciesStore } from '@/stores/speciesStore'
import { useUiStore } from '@/stores/uiStore'
import { FILE_STATUS, JOB_PHASE } from '@/constants/enums'
import { MAX_BATCH_FILES, MAX_FILE_MB } from '@/constants/limits'
import { PATHS } from '@/routes/paths'
import DropZone from '@/components/domain/DropZone'
import ResultHero from '@/components/domain/ResultHero'
import ProbBarChart from '@/components/domain/ProbBarChart'
import Card from '@/components/base/Card'
import Tag from '@/components/base/Tag'
import Alert from '@/components/feedback/Alert'
import EmptyState from '@/components/data/EmptyState'
import { imageContentUrl } from '@/api/images'
import { formatFileSize } from '@/utils/format'

export default function Recognize() {
  const navigate = useNavigate()
  const items = useRecognizeStore((s) => s.items)
  const phase = useRecognizeStore((s) => s.phase)
  const doneCount = useRecognizeStore((s) => s.doneCount)
  const totalCount = useRecognizeStore((s) => s.totalCount)
  const addFiles = useRecognizeStore((s) => s.addFiles)
  const removeItem = useRecognizeStore((s) => s.removeItem)
  const clearAll = useRecognizeStore((s) => s.clearAll)
  const clearSucceeded = useRecognizeStore((s) => s.clearSucceeded)
  const submit = useRecognizeStore((s) => s.submit)
  const retryFailed = useRecognizeStore((s) => s.retryFailed)

  const isLoggedIn = useAuthStore((s) => s.isLoggedIn())
  const guestQuota = useAuthStore((s) => s.guestQuota)
  const openLoginPrompt = useAuthStore((s) => s.openLoginPrompt)
  const ensureSpecies = useSpeciesStore((s) => s.ensureLoaded)
  const toastWarn = useUiStore((s) => s.toast)

  useEffect(() => {
    void ensureSpecies()
  }, [ensureSpecies])

  const busy = phase === JOB_PHASE.UPLOADING || phase === JOB_PHASE.RECOGNIZING
  const successItems = items.filter((i) => i.status === FILE_STATUS.DONE && i.result)
  const failedItems = items.filter((i) => i.status === FILE_STATUS.FAILED)
  const pendingCount = items.filter((i) => i.status !== FILE_STATUS.DONE).length
  const canSubmit = items.length > 0 && pendingCount > 0 && !busy
  const guestRemaining = isLoggedIn ? null : (guestQuota?.remaining ?? 0)

  const handleSubmit = () => {
    if (!isLoggedIn && (guestRemaining ?? 0) <= 0) {
      openLoginPrompt('试用次数已用完，登录后可继续使用')
      return
    }
    if (guestRemaining !== null && pendingCount > guestRemaining) {
      toastWarn(
        `本次待识别 ${pendingCount} 张，但试用仅剩 ${guestRemaining} 次，识别将在额度用尽时停止`,
        'warn',
        5000,
      )
    }
    void submit()
  }

  return (
    <div className="flex flex-col gap-5">
      {/* ── ① 标题 ────────────────────────────────────────── */}
      <header className="flex flex-wrap items-start gap-3 justify-between">
        <div>
          <h1 className="m-0 text-[22px] font-semibold text-ink">识别工作台</h1>
          <p className="m-0 mt-1.5 text-[13.5px] text-ink-2">
            上传水下鱼类图片，获取物种判定与 Top-5 候选。
          </p>
        </div>

        {!isLoggedIn && guestQuota && (
          <Tag tone={guestQuota.remaining > 0 ? 'brand' : 'warn'} dot>
            试用剩余 {guestQuota.remaining} / {guestQuota.quota} 次
          </Tag>
        )}
      </header>

      {/* ── 额度用尽提示 ─────────────────────────────────── */}
      {!isLoggedIn && guestRemaining === 0 && (
        <Alert
          tone="warn"
          title="试用次数已用完"
          action={
            <Link to={PATHS.login} className="no-underline">
              <Button type="primary" size="small">
                登录继续使用
              </Button>
            </Link>
          }
        >
          注册并登录后可无限次识别，历史记录会自动保存。你已上传的图片不会丢失。
        </Alert>
      )}

      {/* ── ② 上传区 ──────────────────────────────────────── */}
      <DropZone existingCount={items.length} disabled={busy} onAccept={addFiles} />

      {/* ── ③ 文件队列 ────────────────────────────────────── */}
      {items.length > 0 && (
        <Card
          title={`待处理图片（${items.length} / ${MAX_BATCH_FILES}）`}
          description={busy ? `正在处理，已完成 ${doneCount} / ${totalCount}` : undefined}
          extra={
            <div className="flex gap-2">
              {successItems.length > 0 && !busy && (
                <Button size="small" onClick={clearSucceeded}>
                  移除已完成的 {successItems.length} 张
                </Button>
              )}
              <Button size="small" danger disabled={busy} onClick={clearAll}>
                清空
              </Button>
            </div>
          }
        >
          <ul className="m-0 p-0 list-none grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((it) => (
              <QueueCard
                key={it.uid}
                item={it}
                onRemove={() => removeItem(it.uid)}
                busy={busy}
              />
            ))}
          </ul>

          <div className="mt-4 flex flex-wrap items-center gap-2.5">
            <Button
              type="primary"
              size="large"
              disabled={!canSubmit}
              loading={busy}
              onClick={handleSubmit}
            >
              {busy ? '识别中…' : `开始识别${pendingCount > 1 ? `（${pendingCount} 张）` : ''}`}
            </Button>

            {failedItems.length > 0 && !busy && (
              <Button size="large" onClick={() => void retryFailed()}>
                重试失败的 {failedItems.length} 张
              </Button>
            )}

            <span className="text-[12.5px] text-ink-3">
              单张不超过 {MAX_FILE_MB}MB，超出部分会在提交时被拒绝
            </span>
          </div>
        </Card>
      )}

      {/* ── ④ 结果区 ──────────────────────────────────────── */}
      {successItems.length === 1 && successItems[0]!.result && (
        <div className="flex flex-col gap-5">
          <ResultHero
            result={successItems[0]!.result!}
            showImage
            imageUrl={imageContentUrl(successItems[0]!.result!.image.id)}
            actions={
              <>
                <Link to={PATHS.history} className="no-underline">
                  <Button>去历史记录查看</Button>
                </Link>
                <Button onClick={clearAll}>再识别一张</Button>
              </>
            }
          />
          <Card title="Top-5 候选物种" description="按模型给出的概率从高到低排列，首位为最终判定结果。">
            <ProbBarChart candidates={successItems[0]!.result!.candidates} />
          </Card>
        </div>
      )}

      {successItems.length > 1 && (
        <Card
          title={`识别结果（${successItems.length} 张成功）`}
          description="点击任意一条查看完整的 Top-5 候选与物种说明。"
        >
          <ul className="m-0 p-0 list-none flex flex-col gap-2.5">
            {successItems.map((it) => {
              const r = it.result!
              return (
                <li
                  key={it.uid}
                  role="button"
                  tabIndex={0}
                  aria-label={`查看 ${r.cn_name} 的 Top-5 详情`}
                  className="flex items-center gap-3.5 rounded-lg border border-line bg-surface-2 px-3.5 py-3 cursor-pointer transition-colors hover:border-line-strong"
                  onClick={() => {
                    // 登录用户 → 记录已存档，跳历史详情看完整 Top-5；
                    // 游客识别不落库（record_id 为 null）→ 弹登录引导。
                    if (r.record_id) {
                      navigate(PATHS.historyDetail(r.record_id))
                    } else {
                      openLoginPrompt('登录后结果自动存档，可随时回看完整 Top-5 候选')
                    }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      if (r.record_id) {
                        navigate(PATHS.historyDetail(r.record_id))
                      } else {
                        openLoginPrompt('登录后结果自动存档，可随时回看完整 Top-5 候选')
                      }
                    }
                  }}
                >
                  <img
                    src={imageContentUrl(r.image.id)}
                    alt={r.cn_name}
                    className="shrink-0 object-cover border border-line"
                    style={{ width: 48, height: 48, borderRadius: 'var(--radius)' }}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="m-0 text-[14px] font-medium text-ink truncate">{r.cn_name}</p>
                    <p className="m-0 mt-0.5 text-[12px] italic text-ink-2 truncate">{r.latin_name}</p>
                  </div>
                  <span className="shrink-0 text-[13.5px] num text-brand-600 font-semibold">
                    {(r.confidence * 100).toFixed(1)}%
                  </span>
                </li>
              )
            })}
          </ul>
        </Card>
      )}

      {/* ── 全失败空态 ────────────────────────────────────── */}
      {items.length > 0 && failedItems.length === items.length && !busy && (
        <EmptyState
          title="这批图片都没有识别成功"
          description="可能是图片不清晰、主体过小，或识别服务暂时不可用。已经消耗的算力不会退回，但你可以直接重试。"
          action={
            <Button type="primary" onClick={() => void retryFailed()}>
              重新识别
            </Button>
          }
          hint="若反复失败，建议更换主体更清晰、光线更均匀的图片"
        />
      )}
    </div>
  )
}

/* ── 队列缩略卡（C-27 ThumbCard）──────────────────────────────── */

import type { QueueItem } from '@/stores/recognizeStore'

function QueueCard({
  item,
  onRemove,
  busy,
}: {
  item: QueueItem
  onRemove: () => void
  busy: boolean
}) {
  const STATUS_META: Record<string, { tone: 'muted' | 'brand' | 'ok' | 'warn' | 'danger'; label: string }> = {
    [FILE_STATUS.PENDING]: { tone: 'muted', label: '待上传' },
    [FILE_STATUS.UPLOADING]: { tone: 'brand', label: `上传中 ${item.progress}%` },
    [FILE_STATUS.UPLOADED]: { tone: 'brand', label: '待识别' },
    [FILE_STATUS.RECOGNIZING]: { tone: 'brand', label: '识别中' },
    [FILE_STATUS.DONE]: { tone: 'ok', label: '已完成' },
    [FILE_STATUS.FAILED]: { tone: 'danger', label: '失败' },
  }
  const meta = STATUS_META[item.status] ?? STATUS_META[FILE_STATUS.PENDING]!

  return (
    <li className="relative rounded-lg border border-line bg-surface-2 overflow-hidden">
      <div className="flex gap-3 p-3">
        {/* 缩略图 */}
        <div className="relative shrink-0">
          {item.previewUrl ? (
            <img
              src={item.previewUrl}
              alt={item.file.name}
              className="object-cover border border-line"
              style={{ width: 56, height: 56, borderRadius: 'var(--radius)' }}
            />
          ) : (
            <div
              className="border border-line"
              style={{ width: 56, height: 56, borderRadius: 'var(--radius)', background: 'var(--surface-3)' }}
            />
          )}
          {/* 上传进度条（z-index 2 局部叠层） */}
          {item.status === FILE_STATUS.UPLOADING && (
            <div
              className="absolute left-0 bottom-0 w-full"
              style={{ height: 3, background: 'var(--surface-3)', borderRadius: '0 0 var(--radius) var(--radius)' }}
            >
              <div
                style={{
                  width: `${item.progress}%`,
                  height: '100%',
                  background: 'var(--primary)',
                  transition: 'width 200ms linear',
                }}
              />
            </div>
          )}
        </div>

        {/* 信息 */}
        <div className="flex-1 min-w-0">
          <p className="m-0 text-[13px] text-ink truncate" title={item.file.name}>
            {item.file.name}
          </p>
          <p className="m-0 mt-0.5 text-[11.5px] text-ink-3 num">{formatFileSize(item.file.size)}</p>
          <div className="mt-1.5">
            <Tag tone={meta.tone} dot>
              {meta.label}
            </Tag>
          </div>
        </div>

        {/* 移除按钮 */}
        {!busy && item.status !== FILE_STATUS.DONE && (
          <button
            type="button"
            aria-label={`移除 ${item.file.name}`}
            onClick={onRemove}
            className="absolute top-2 right-2 p-1 rounded-sm border-0 bg-transparent text-ink-3 hover:text-danger hover:bg-danger-50 transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
            </svg>
          </button>
        )}
      </div>

      {/* 失败原因（就地说明，不弹窗） */}
      {item.status === FILE_STATUS.FAILED && item.error && (
        <p
          className="m-0 px-3 py-2 text-[12px] leading-[1.5] border-t"
          style={{ background: 'var(--danger-50)', color: 'var(--danger)', borderColor: 'var(--danger-border)' }}
        >
          {item.error}
        </p>
      )}
    </li>
  )
}
