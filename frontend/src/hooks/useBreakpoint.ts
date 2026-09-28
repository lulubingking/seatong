/**
 * 断点判定 hook
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §8.1.1（断点定义）
 *
 * 断点（max-width 语义，单位 px）：
 *   XS  < 768        手机竖屏
 *   SM  768 ～ 1023  平板竖屏 / 手机横屏
 *   MD  1024 ～ 1439 笔记本
 *   LG  ≥ 1440       大屏
 *
 * 【为何不用 matchMedia 组 + SSR 判断】本应用无 SSR，
 * 直接用 `window.innerWidth` 并监听 resize 即可，避免 matchMedia 的多监听器泄漏。
 * ────────────────────────────────────────────────────────────────
 */

import { useEffect, useState } from 'react'
import { BP_LG, BP_MD, BP_SM } from '@/constants/limits'
import { BREAKPOINT, type Breakpoint } from '@/constants/enums'

function calc(w: number): Breakpoint {
  if (w >= BP_LG) return BREAKPOINT.LG
  if (w >= BP_MD) return BREAKPOINT.MD
  if (w >= BP_SM) return BREAKPOINT.SM
  return BREAKPOINT.XS
}

export interface BreakpointInfo {
  breakpoint: Breakpoint
  width: number
  /** < 768 —— 表格须卡片化（D9 §8.1.3） */
  isMobile: boolean
  /** 768 ～ 1023 */
  isTablet: boolean
  /** ≥ 1024 —— 可展示完整表格与多列布局 */
  isDesktop: boolean
}

export function useBreakpoint(): BreakpointInfo {
  const [width, setWidth] = useState<number>(() =>
    typeof window === 'undefined' ? BP_LG : window.innerWidth,
  )

  useEffect(() => {
    let raf = 0
    const onResize = () => {
      // rAF 节流，避免拖拽窗口时高频 setState
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => setWidth(window.innerWidth))
    }
    window.addEventListener('resize', onResize)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', onResize)
    }
  }, [])

  const breakpoint = calc(width)
  return {
    breakpoint,
    width,
    isMobile: width < BP_SM,
    isTablet: width >= BP_SM && width < BP_MD,
    isDesktop: width >= BP_MD,
  }
}
