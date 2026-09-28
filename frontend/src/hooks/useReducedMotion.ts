/**
 * 减少动效偏好 hook
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §8.3.6（动效与偏好尊重）
 *
 * 【硬约束】所有动效必须尊重 `prefers-reduced-motion: reduce`。
 * CSS 层已在 tokens.css 中做全局压缩，本 hook 用于 **JS 驱动**的动效
 * （如 Top-5 条形图的宽度过渡、Toast 进出场）在偏好开启时直接跳到终态。
 * ────────────────────────────────────────────────────────────────
 */

import { useEffect, useState } from 'react'
import { MOTION_BAR, MOTION_MAX, MOTION_MIN } from '@/constants/limits'

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  return reduced
}

/**
 * 返回按偏好调整后的时长。
 * @param ms 期望时长（微交互 150–300 ms；条形图为 450 ms 例外）
 */
export function useMotionDuration(ms: number = MOTION_MAX): number {
  const reduced = useReducedMotion()
  return reduced ? 0 : Math.min(Math.max(ms, MOTION_MIN), ms)
}

export { MOTION_BAR, MOTION_MIN, MOTION_MAX }
