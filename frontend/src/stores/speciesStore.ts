/**
 * 物种字典缓存
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §10.5（物种字典的缓存策略）
 *
 * 【纪律 §9.2.1】前端**不得**硬编码 `class_index → 物种名` 映射。
 * 本 store 是全前端获取物种信息的唯一途径。
 *
 * 缓存策略：应用启动后**懒加载一次**，缓存于**内存**（不写 localStorage，
 * 避免数据陈旧）。识别结果中若已内联 species 对象，优先用内联值。
 * ────────────────────────────────────────────────────────────────
 */

import { create } from 'zustand'
import * as speciesApi from '@/api/species'
import type { Species } from '@/api/types'

export interface SpeciesState {
  /** class_index → Species */
  map: Record<number, Species>
  loaded: boolean
  loading: boolean
  error: string | null

  /** 懒加载一次；已加载则直接返回 */
  ensureLoaded: () => Promise<void>
  /** 强制重载（管理端改动物种信息后调用） */
  reload: () => Promise<void>
  /** 按 index 取物种；未加载返回 null（调用方自行处理降级） */
  get: (classIndex: number) => Species | null
  /** 全量列表（按 class_index 升序） */
  list: () => Species[]
  /** 把接口内联返回的 species 合并进缓存（减少后续请求） */
  merge: (s: Species) => void
}

export const useSpeciesStore = create<SpeciesState>((set, get) => ({
  map: {},
  loaded: false,
  loading: false,
  error: null,

  async ensureLoaded() {
    if (get().loaded || get().loading) return
    set({ loading: true, error: null })
    try {
      const out = await speciesApi.listSpecies()
      const map: Record<number, Species> = {}
      for (const s of out.items) map[s.class_index] = s
      set({ map, loaded: true, loading: false })
    } catch (e) {
      set({
        loading: false,
        error: e instanceof Error ? e.message : '物种信息加载失败',
      })
    }
  },

  async reload() {
    set({ loaded: false, loading: false })
    await get().ensureLoaded()
  },

  get(index) {
    return get().map[index] ?? null
  },

  list() {
    return Object.values(get().map).sort((a, b) => a.class_index - b.class_index)
  },

  merge(s) {
    set((st) => ({ map: { ...st.map, [s.class_index]: s } }))
  },
}))

/* ── 非钩子场景的取值 ────────────────────────────────────────── */

/**
 * 取物种显示名。**不在缓存中时返回 `#${index}` 而非猜测名称** ——
 * 宁可显示占位也不显示错误物种名。
 */
export function speciesName(classIndex: number): string {
  return useSpeciesStore.getState().map[classIndex]?.cn_name ?? `#${classIndex}`
}

/** 取拉丁学名。`fish_18`（鹦嘴鱼科，未定种）后端返回科名，前端原样展示 */
export function speciesLatin(classIndex: number): string {
  return useSpeciesStore.getState().map[classIndex]?.latin_name ?? '—'
}
