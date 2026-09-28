/**
 * 页面 7 · 历史详情 `/history/:id`（视图 `historyDetail`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.7
 *
 * 需求锚点：FR-HISTORY-03、FR-RESULT-01～06、BR-HISTORY-09、BR-RESULT-08、BR-RECOG-10
 *
 * 布局骨架：
 *   ① 面包屑 + 返回
 *   ② 原图区（左）/ 首位结果卡（右）—— 桌面两栏，移动单列
 *   ③ Top-5 候选条形图
 *   ④ 物种知识块（形态 / 习性 / 分布）
 *   ⑤ 元信息表（记录 ID / 耗时 / 模型版本 / 识别时间）
 *   ⑥ 操作（删除本条 / 返回列表）
 *
 * 区块级错误处理：
 *   40401 → 整页转 NotFound 兜底视图（记录不存在或非本人所有，不区分二者）
 *   40402 → 图片区用占位块，**其余内容正常渲染**（原图过期不影响结果）
 * ────────────────────────────────────────────────────────────────
 */

import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button, Popconfirm } from 'antd'
import * as recordsApi from '@/api/records'
import { imageContentUrl } from '@/api/images'
import { isApiError } from '@/api/client'
import { useUiStore } from '@/stores/uiStore'
import { CONFIG_KEYS } from '@/api/types'
import * as configApi from '@/api/config'
import { PATHS } from '@/routes/paths'
import { RECORD_STATUS_META } from '@/constants/enums'
import type { RecordDetailOut } from '@/api/types'
import Card from '@/components/base/Card'
import Tag from '@/components/base/Tag'
import Alert from '@/components/feedback/Alert'
import ProbBarChart from '@/components/domain/ProbBarChart'
import ResultHero from '@/components/domain/ResultHero'
import PageSkeleton from '@/components/feedback/PageSkeleton'
import NotFound from '@/pages/NotFound'
import { formatDateTime, formatDuration, formatFileSize } from '@/utils/format'

export default function HistoryDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const toastOk = useUiStore((s) => s.toast)
  const toastErr = useUiStore((s) => s.toast)

  const [data, setData] = useState<RecordDetailOut | null>(null)
  const [loading, setLoading] = useState(true)
  /** null = 无错误；否则为已归一化的错误码 */
  const [errCode, setErrCode] = useState<string | null>(null)
  const [errMsg, setErrMsg] = useState<string | null>(null)
  const [retentionDays, setRetentionDays] = useState<number | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setErrCode(null)
    setErrMsg(null)
    try {
      const out = await recordsApi.getHistoryDetail(id)
      setData(out)
    } catch (e) {
      if (isApiError(e)) {
        setErrCode(e.code)
        setErrMsg(e.message)
      } else {
        setErrCode('50001')
        setErrMsg('服务出现异常，请稍后重试')
      }
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  // 留存期（用于 40402 的说明文案）
  useEffect(() => {
    configApi
      .getConfig()
      .then((items) => {
        const it = items.find((c) => c.config_key === CONFIG_KEYS.IMAGE_RETENTION_DAYS)
        if (it) setRetentionDays(Number(it.value))
      })
      .catch(() => {
        /* 非管理员无权读配置 → 保持 null，文案降级为不写具体天数 */
      })
  }, [])

  const remove = async () => {
    if (!id) return
    try {
      await recordsApi.deleteOneRecord(id)
      toastOk('记录已删除')
      navigate(PATHS.history, { replace: true })
    } catch (e) {
      toastErr(isApiError(e) ? e.message : '删除失败，请稍后重试', 'danger')
    }
  }

  /* ── 40401：整页转兜底（不区分「不存在」与「非本人」，防 ID 枚举）── */
  if (errCode === '40401') {
    return <NotFound />
  }

  if (loading) return <PageSkeleton variant="list" rows={3} />

  if (errCode) {
    return (
      <div className="flex flex-col gap-4">
        <Alert
          tone="danger"
          title="记录加载失败"
          action={
            <Button size="small" onClick={() => void load()}>
              重试
            </Button>
          }
        >
          {errMsg}
        </Alert>
        <div>
          <Link to={PATHS.history} className="no-underline">
            <Button>返回历史记录</Button>
          </Link>
        </div>
      </div>
    )
  }

  if (!data) return null

  const { record, candidates, species, image } = data
  /** 原图不可用（已过期 / 已删除）→ 区块级提示，其余照常 */
  const imageMissing = !image

  return (
    <div className="flex flex-col gap-5">
      {/* ── ① 面包屑 ──────────────────────────────────────── */}
      <nav className="flex items-center gap-1.5 text-[12.5px] text-ink-3" aria-label="面包屑">
        <Link to={PATHS.history} className="text-ink-2 underline underline-offset-2">
          历史记录
        </Link>
        <span aria-hidden="true">/</span>
        <span>详情</span>
      </nav>

      <header className="flex flex-wrap items-start gap-3 justify-between">
        <div>
          <h1 className="m-0 text-[22px] font-semibold text-ink">识别详情</h1>
          <p className="m-0 mt-1.5 text-[13px] text-ink-2 num">
            {formatDateTime(record.created_at)}
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <Tag tone={RECORD_STATUS_META[record.status].tone} dot>
            {RECORD_STATUS_META[record.status].label}
          </Tag>
          <Popconfirm
            title="删除这条记录？"
            description="删除后该识别结果将不再显示，此操作不可撤销。"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
            onConfirm={() => void remove()}
          >
            <Button danger>删除记录</Button>
          </Popconfirm>
        </div>
      </header>

      {/* ── ② 原图 + 首位结果（两栏）──────────────────────── */}
      <div className="grid gap-5 grid-cols-1 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <Card title="原图" padding="sm">
          {imageMissing ? (
            /* 40402 区块级：仅图片区受影响 */
            <div
              className="flex flex-col items-center justify-center text-center py-10 px-4 border border-dashed"
              style={{ borderRadius: 'var(--radius-lg)', borderColor: 'var(--border-strong)' }}
            >
              <span
                aria-hidden="true"
                className="mb-2.5 flex items-center justify-center rounded-full"
                style={{ width: 40, height: 40, background: 'var(--warn-50)', color: 'var(--warn)' }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <path d="M12 3.8 21.2 20H2.8L12 3.8Z" stroke="currentColor" strokeWidth="1.9" strokeLinejoin="round" />
                  <path d="M12 10v4.2" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
                  <circle cx="12" cy="17.2" r="1" fill="currentColor" />
                </svg>
              </span>
              <p className="m-0 text-[13.5px] font-medium text-ink">原图已不可用</p>
              <p className="m-0 mt-1.5 text-[12.5px] text-ink-2 leading-[1.6] max-w-[280px]">
                上传的图片{retentionDays ? `默认保留 ${retentionDays} 天` : '有保留期限'}，
                超期后由系统自动清理。识别结果与物种信息不受影响。
              </p>
            </div>
          ) : (
            <figure className="m-0">
              <img
                src={imageContentUrl(image.id)}
                alt={`${record.cn_name} 的识别原图`}
                className="w-full object-contain border border-line"
                style={{ borderRadius: 'var(--radius)', background: 'var(--surface-3)', maxHeight: 360 }}
              />
              <figcaption className="mt-3 text-[12px] text-ink-3 leading-[1.7]">
                <span className="block truncate" title={image.original_filename}>
                  {image.original_filename}
                </span>
                <span className="num">
                  {image.width} × {image.height} · {formatFileSize(image.file_size)}
                </span>
              </figcaption>
            </figure>
          )}
        </Card>

        {/* 首位结果（复用 ResultHero —— 但不重复渲染知识块） */}
        <ResultHero
          result={{
            record_id: record.id,
            image: image ?? {
              id: record.image_id ?? '',
              original_filename: '',
              mime_type: '',
              file_size: 0,
              width: 0,
              height: 0,
              content_hash: '',
              created_at: record.created_at,
              expires_at: 0,
            },
            class_index: record.class_index,
            cn_name: record.cn_name,
            latin_name: record.latin_name,
            confidence: record.confidence,
            is_low_confidence: record.is_low_confidence,
            candidates,
            species: species ?? EMPTY_SPECIES,
            duration_ms: record.duration_ms,
            model_version: '',
            guest_quota: null,
          }}
        />
      </div>

      {/* ── ③ Top-5 候选 ──────────────────────────────────── */}
      <Card
        title="Top-5 候选物种"
        description="按模型给出的概率从高到低排列。首位为最终判定结果，其余为备选参考。"
      >
        <ProbBarChart candidates={candidates} highlightIndex={record.class_index} />
      </Card>

      {/* ── ④ 元信息 ──────────────────────────────────────── */}
      <Card title="记录信息">
        <dl className="m-0 grid gap-x-6 gap-y-3.5 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 text-[13px]">
          <Meta label="记录 ID" value={record.id} mono />
          <Meta label="物种编号" value={`#${record.class_index}（class_index）`} mono />
          <Meta label="识别耗时" value={formatDuration(record.duration_ms)} mono />
          <Meta label="识别时间" value={formatDateTime(record.created_at)} mono />
          {image && <Meta label="原图尺寸" value={`${image.width} × ${image.height}`} mono />}
          {image && (
            <Meta
              label="原图保留至"
              value={formatDateTime(image.expires_at)}
              mono
            />
          )}
        </dl>
      </Card>

      <div>
        <Link to={PATHS.history} className="no-underline">
          <Button>返回历史记录</Button>
        </Link>
      </div>
    </div>
  )
}

/* ── 局部组件 ────────────────────────────────────────────────── */

function Meta({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="m-0 text-[12px] text-ink-3">{label}</dt>
      <dd className={`m-0 mt-0.5 text-ink break-all ${mono ? 'num' : ''}`}>{value}</dd>
    </div>
  )
}

/** 物种信息缺失时的占位（正常情况下后端总会返回 species） */
const EMPTY_SPECIES = {
  class_index: -1,
  cn_name: '',
  latin_name: '',
  common_name: '',
  morphology: '',
  habit: '',
  distribution: '',
  image_path: null,
}
