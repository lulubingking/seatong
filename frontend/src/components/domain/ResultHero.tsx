/**
 * C-43 ResultHero —— 首位结果卡
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §4.5 C-43、§5.2（识别工作台结果区）
 *
 * 承载：物种中文名（大字号）· 拉丁学名 · 置信度 · 低置信度提示 · 耗时
 *
 * 【文案纪律】`fish_18`（鹦嘴鱼科）为科级未定种 —— 拉丁名位置显示后端下发的
 * 科名字符串（`Scaridae`），**不得**在前端伪造二名法（D9 §9.2.1）。
 *
 * 【数字纪律】置信度 1 位小数；耗时整数 ms；极小概率显示 `< 0.1%`。
 * ────────────────────────────────────────────────────────────────
 */

import type { ReactNode } from 'react'
import type { RecognizeOut } from '@/api/types'
import Tag from '@/components/base/Tag'
import Alert from '@/components/feedback/Alert'
import { formatConfidence, formatDuration } from '@/utils/format'
import { toConfidenceTier, CONFIDENCE_TIER_META } from '@/constants/enums'

export interface ResultHeroProps {
  result: RecognizeOut
  /** 原图预览（已在别处展示时可传 false） */
  showImage?: boolean
  imageUrl?: string | null
  /** 底部操作区（如「查看详情」「再次识别」） */
  actions?: ReactNode
}

export default function ResultHero({
  result,
  showImage = false,
  imageUrl,
  actions,
}: ResultHeroProps) {
  const tier = toConfidenceTier(result.confidence)
  const meta = CONFIDENCE_TIER_META[tier]
  const lowConf = result.is_low_confidence

  return (
    <section className="rounded-lg border border-line bg-surface overflow-hidden">
      {/* ── 首位判定区 ─────────────────────────────────── */}
      <div className="px-5 py-5 sm:px-6 sm:py-6" style={{ background: 'var(--primary-50)' }}>
        <div className="flex items-start gap-4">
          {showImage && imageUrl && (
            <img
              src={imageUrl}
              alt="待识别的鱼类图片"
              className="shrink-0 object-cover border border-line"
              style={{ width: 88, height: 88, borderRadius: 'var(--radius)' }}
            />
          )}

          <div className="flex-1 min-w-0">
            <p className="m-0 mb-1.5 text-[12.5px]" style={{ color: 'var(--primary-600)' }}>
              识别结果
            </p>

            <h2 className="m-0 text-[22px] sm:text-[26px] font-semibold leading-[1.25] text-ink">
              {result.cn_name}
            </h2>

            <p className="m-0 mt-1 text-[13px] italic text-ink-2">{result.latin_name}</p>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span
                className="inline-flex items-baseline gap-1 px-2.5 py-1 rounded-full text-[13px] num"
                style={{ background: 'var(--surface)', color: 'var(--primary-600)', fontWeight: 600 }}
              >
                置信度 {formatConfidence(result.confidence)}
              </span>
              <Tag tone={meta.tone === 'ok' ? 'ok' : meta.tone === 'accent' ? 'accent' : 'warn'}>
                {meta.label}
              </Tag>
              <span className="text-[12.5px] text-ink-2 num">耗时 {formatDuration(result.duration_ms)}</span>
            </div>
          </div>
        </div>

        {/* 低置信度强化提示 */}
        {lowConf && (
          <Alert tone="warn" className="mt-4">
            {meta.hint}。建议对照下方 Top-5 候选一并判断，或更换主体更清晰、
            光线更均匀的图片重新识别。
          </Alert>
        )}
      </div>

      {/* ── 物种知识区 ─────────────────────────────────── */}
      {result.species && (
        <div className="px-5 py-5 sm:px-6 border-t border-line">
          <KnowledgeBlock label="形态特征" text={result.species.morphology} />
          <KnowledgeBlock label="生活习性" text={result.species.habit} />
          <KnowledgeBlock label="分布区域" text={result.species.distribution} />
        </div>
      )}

      {actions && (
        <div className="px-5 py-4 sm:px-6 border-t border-line flex flex-wrap gap-2.5">
          {actions}
        </div>
      )}
    </section>
  )
}

function KnowledgeBlock({ label, text }: { label: string; text: string }) {
  if (!text) return null
  return (
    <div className="mb-4 last:mb-0">
      <h3 className="m-0 mb-1.5 text-[13px] font-semibold text-ink-2">{label}</h3>
      <p className="m-0 text-[13.5px] leading-[1.75] text-ink">{text}</p>
    </div>
  )
}
