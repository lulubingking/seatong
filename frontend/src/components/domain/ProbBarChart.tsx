/**
 * C-26 ProbBarChart —— Top-5 概率条形图
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §4.3 C-26、§3.6（度量色与数字排版）、BR-RESULT-03
 *
 * 【核心设计】首位 vs 其余用**色相区分**而非 5 种颜色：
 *   首位      → `--primary`（品牌色，视觉权重最高）
 *   非首位    → `--metric`（中性灰）
 *   理由：用单一主色 + 中性灰比用 5 种不同颜色更能表达
 *   「第一位是答案，其余是备选」的层级关系，且避免用户误读为 5 个并列分类。
 *
 * 【数字纪律】置信度保留 1 位小数，极小值显示 `< 0.1%`（D-02 / D-03）。
 * 【动效纪律】填充动画 450 ms（显式例外，见 §3.9）；仅用 width 过渡；
 *   `prefers-reduced-motion` 时直接跳至终态。
 * ────────────────────────────────────────────────────────────────
 */

import { useEffect, useState } from 'react'
import type { Candidate } from '@/api/types'
import { formatConfidence } from '@/utils/format'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import { MOTION_BAR } from '@/constants/limits'

export interface ProbBarChartProps {
  candidates: Candidate[]
  /** 高亮的 class_index（通常是首位）。用于详情页对比时跨记录高亮同一物种 */
  highlightIndex?: number
}

export default function ProbBarChart({ candidates, highlightIndex }: ProbBarChartProps) {
  const reduced = useReducedMotion()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    if (reduced) {
      setMounted(true)
      return
    }
    const id = requestAnimationFrame(() => setMounted(true))
    return () => cancelAnimationFrame(id)
  }, [reduced])

  if (!candidates || candidates.length === 0) return null

  const max = Math.max(...candidates.map((c) => c.confidence), 0.0001)

  return (
    <ul className="m-0 p-0 list-none flex flex-col gap-3" role="list">
      {candidates.map((c, i) => {
        const isFirst = highlightIndex !== undefined ? c.class_index === highlightIndex : i === 0
        const fill = isFirst ? 'var(--primary)' : 'var(--metric)'
        // 相对最大值归一化，使首位视觉占比最大但其余仍可辨
        const pct = Math.max(2, (c.confidence / max) * 100)

        return (
          <li key={`${c.class_index}-${c.rank}`}>
            <div className="flex items-baseline gap-2 mb-1.5">
              <span
                className="shrink-0 text-[12.5px] num"
                style={{ color: isFirst ? 'var(--primary-600)' : 'var(--text-3)', fontWeight: isFirst ? 600 : 400 }}
              >
                #{c.rank}
              </span>
              <span
                className="flex-1 min-w-0 truncate text-[13.5px]"
                style={{ color: isFirst ? 'var(--text)' : 'var(--text-2)', fontWeight: isFirst ? 600 : 400 }}
              >
                {c.cn_name}
              </span>
              <span
                className="shrink-0 text-[13px] num tabular-nums"
                style={{ color: isFirst ? 'var(--primary-600)' : 'var(--metric-deep)', fontWeight: isFirst ? 600 : 400 }}
              >
                {formatConfidence(c.confidence)}
              </span>
            </div>
            <div
              className="w-full overflow-hidden"
              style={{ height: 8, background: 'var(--surface-3)', borderRadius: 5 }}
              role="img"
              aria-label={`${c.cn_name} 置信度 ${formatConfidence(c.confidence)}`}
            >
              <div
                style={{
                  width: mounted ? `${pct}%` : '0%',
                  height: '100%',
                  background: fill,
                  borderRadius: 5,
                  transition: reduced ? 'none' : `width ${MOTION_BAR}ms cubic-bezier(.4,0,.2,1)`,
                }}
              />
            </div>
            <p className="m-0 mt-1 text-[11.5px] text-ink-3 italic">{c.latin_name}</p>
          </li>
        )
      })}
    </ul>
  )
}
