/**
 * 识别作业状态机 store
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §6.1（识别作业状态机）、§6.4（批量上传并发编排）、§10.5
 *
 * 【为什么识别状态必须放全局 store 而不是页面局部状态】
 *   识别作业具有**跨路由的持续性**：用户在识别进行中切到历史记录页再切回来，
 *   进行中的作业不应丢失。局部状态会在组件卸载时销毁。
 *
 * 【纪律】状态用**单一 `phase` 字段**驱动，禁止用多个布尔标志拼凑
 *   （`isLoading && hasResult && !isError` 这类写法在批量场景必然出现
 *   不可达状态组合）。D9 §10.7 自检项明确要求。
 * ────────────────────────────────────────────────────────────────
 */

import { create } from 'zustand'
import * as imagesApi from '@/api/images'
import * as recognizeApi from '@/api/recognize'
import { isApiError } from '@/api/client'
import { FILE_STATUS, JOB_PHASE, type FileStatus, type JobPhase } from '@/constants/enums'
import { MAX_BATCH_FILES, TOP_K, UPLOAD_CONCURRENCY } from '@/constants/limits'
import type { RecognizeOut } from '@/api/types'
import { useAuthStore } from './authStore'

/** 队列中的单个文件条目 */
export interface QueueItem {
  /** 本地唯一键（`File` 无 id，用自增序号 + name 组合） */
  uid: string
  file: File
  /** 本地预览 URL（`URL.createObjectURL`），移除时须 revoke */
  previewUrl: string | null
  status: FileStatus
  /** 上传进度 0–100 */
  progress: number
  /** 上传成功后拿到的图片资源 ID */
  imageId: string | null
  /** 识别结果 */
  result: RecognizeOut | null
  /** 失败原因（已归一化文案） */
  error: string | null
  /** 失败项的业务码，供「是否可重试」判定 */
  errorCode: string | null
}

let uidSeq = 0

export interface RecognizeState {
  phase: JobPhase
  items: QueueItem[]
  /** 批次内已完成识别的条数（用于进度展示） */
  doneCount: number
  /** 用户点「开始识别」时锁定的张数（避免中途增删导致分母跳动） */
  totalCount: number

  /* ── 派生 ── */
  canSubmit: () => boolean
  successItems: () => QueueItem[]

  /* ── 动作 ── */
  addFiles: (files: File[]) => void
  removeItem: (uid: string) => void
  clearAll: () => void
  /** 移除全部已成功的条目（保留失败的，便于重试） */
  clearSucceeded: () => void

  /** 提交：先并发上传（池 = 3），再**串行**识别（单实例防 OOM） */
  submit: () => Promise<void>
  /** 仅重试失败项 */
  retryFailed: () => Promise<void>
  reset: () => void
}

export const useRecognizeStore = create<RecognizeState>((set, get) => ({
  phase: JOB_PHASE.IDLE,
  items: [],
  doneCount: 0,
  totalCount: 0,

  canSubmit() {
    const { items, phase } = get()
    if (phase === JOB_PHASE.UPLOADING || phase === JOB_PHASE.RECOGNIZING) return false
    return items.length > 0 && items.some((i) => i.status !== FILE_STATUS.DONE)
  },

  successItems() {
    return get().items.filter((i) => i.status === FILE_STATUS.DONE && i.result)
  },

  addFiles(files) {
    const room = Math.max(0, MAX_BATCH_FILES - get().items.length)
    const slice = files.slice(0, room)
    const newItems: QueueItem[] = slice.map((file) => ({
      uid: `q${++uidSeq}`,
      file,
      previewUrl: URL.createObjectURL(file),
      status: FILE_STATUS.PENDING,
      progress: 0,
      imageId: null,
      result: null,
      error: null,
      errorCode: null,
    }))
    set((s) => ({
      items: [...s.items, ...newItems],
      phase: JOB_PHASE.READY,
      doneCount: 0,
      totalCount: 0,
    }))
  },

  removeItem(uid) {
    const target = get().items.find((i) => i.uid === uid)
    if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl)
    set((s) => {
      const items = s.items.filter((i) => i.uid !== uid)
      return { items, phase: items.length === 0 ? JOB_PHASE.IDLE : s.phase }
    })
  },

  clearAll() {
    for (const i of get().items) if (i.previewUrl) URL.revokeObjectURL(i.previewUrl)
    set({ items: [], phase: JOB_PHASE.IDLE, doneCount: 0, totalCount: 0 })
  },

  clearSucceeded() {
    const keep = get().items.filter((i) => i.status !== FILE_STATUS.DONE)
    for (const i of get().items) {
      if (i.status === FILE_STATUS.DONE && i.previewUrl) URL.revokeObjectURL(i.previewUrl)
    }
    set({ items: keep, phase: keep.length ? JOB_PHASE.PARTIAL : JOB_PHASE.IDLE })
  },

  /* ── 串行识别（含额度中断处理）─────────────────────────────── */

  async submit() {
    const auth = useAuthStore.getState()
    const needsRecognize = get().items.filter(
      (i) => i.status !== FILE_STATUS.DONE && i.status !== FILE_STATUS.UPLOADING,
    )
    if (needsRecognize.length === 0) return

    // 额度前置门禁（D9 §6.2）：游客额度不足时直接弹登录引导，不发请求
    if (!auth.isLoggedIn()) {
      const remaining = auth.guestQuota?.remaining ?? 3
      if (remaining <= 0) {
        auth.openLoginPrompt('试用次数已用完，登录后可继续使用')
        set({ phase: JOB_PHASE.FAILED })
        return
      }
    }

    set({
      phase: JOB_PHASE.UPLOADING,
      doneCount: 0,
      totalCount: needsRecognize.length,
    })

    // ── 阶段一：并发上传（池 = 3，D9 §6.4）──────────────────
    await runPool(
      needsRecognize,
      UPLOAD_CONCURRENCY,
      async (item) => {
        patchItem(set, get, item.uid, { status: FILE_STATUS.UPLOADING, progress: 0 })
        try {
          const out = await imagesApi.uploadImage(item.file, (p) =>
            patchItem(set, get, item.uid, { progress: p }),
          )
          patchItem(set, get, item.uid, {
            status: FILE_STATUS.UPLOADED,
            progress: 100,
            imageId: out.image.id,
            error: null,
            errorCode: null,
          })
        } catch (e) {
          const msg = isApiError(e) ? e.message : '上传失败，请重试'
          patchItem(set, get, item.uid, {
            status: FILE_STATUS.FAILED,
            error: msg,
            errorCode: isApiError(e) ? e.code : 'NET-01',
          })
        }
      },
    )

    const uploaded = get().items.filter(
      (i) => i.status === FILE_STATUS.UPLOADED && i.imageId,
    )
    if (uploaded.length === 0) {
      set({ phase: JOB_PHASE.UPLOAD_FAILED })
      return
    }

    // ── 阶段二：串行识别（防 OOM + 可预期耗时）──────────────
    set({ phase: JOB_PHASE.RECOGNIZING })

    for (const it of uploaded) {
      const cur = get().items.find((i) => i.uid === it.uid)
      if (!cur?.imageId) continue
      patchItem(set, get, it.uid, { status: FILE_STATUS.RECOGNIZING })
      try {
        const res = await recognizeApi.recognize({
          image_id: cur.imageId,
          top_k: TOP_K,
        })
        patchItem(set, get, it.uid, {
          status: FILE_STATUS.DONE,
          result: res,
          error: null,
          errorCode: null,
        })
        // 额度校准：以服务端返回为准（比本地乐观扣减可靠）
        if (res.guest_quota) {
          useAuthStore.setState({ guestQuota: res.guest_quota })
        } else {
          useAuthStore.getState().consumeQuota()
        }
        set((s) => ({ doneCount: s.doneCount + 1 }))
      } catch (e) {
        const code = isApiError(e) ? e.code : 'NET-01'
        const msg = isApiError(e) ? e.message : '识别失败，请重试'
        patchItem(set, get, it.uid, {
          status: FILE_STATUS.FAILED,
          error: msg,
          errorCode: code,
        })

        // 额度耗尽 → 中断后续识别（已成功的结果保留）
        if (code === '42901') {
          useAuthStore.getState().openLoginPrompt(msg)
          await useAuthStore.getState().refreshQuota()
          break
        }
        // 其余错误（除 50002 不扣额度外）→ 主动校准额度
        if (code !== '50002') {
          await useAuthStore.getState().refreshQuota()
        }
      }
    }

    const final = get().items
    const ok = final.filter((i) => i.status === FILE_STATUS.DONE).length
    const bad = final.filter((i) => i.status === FILE_STATUS.FAILED).length
    set({
      phase:
        bad === 0
          ? JOB_PHASE.DONE
          : ok === 0
            ? JOB_PHASE.FAILED
            : JOB_PHASE.PARTIAL,
    })
  },

  async retryFailed() {
    const failed = get().items.filter((i) => i.status === FILE_STATUS.FAILED)
    // 有 imageId 的直接重跑推理（不重复上传，不重复扣额度外的资源）
    // 无 imageId 的需重新上传
    const needUpload = failed.filter((i) => !i.imageId)
    for (const i of failed) {
      patchItem(set, get, i.uid, {
        status: i.imageId ? FILE_STATUS.UPLOADED : FILE_STATUS.PENDING,
        error: null,
        errorCode: null,
        progress: i.imageId ? 100 : 0,
      })
    }
    if (needUpload.length > 0) {
      set({ phase: JOB_PHASE.UPLOADING })
    } else {
      set({ phase: JOB_PHASE.RECOGNIZING })
    }
    await get().submit()
  },

  reset() {
    for (const i of get().items) if (i.previewUrl) URL.revokeObjectURL(i.previewUrl)
    set({ items: [], phase: JOB_PHASE.IDLE, doneCount: 0, totalCount: 0 })
  },
}))

/* ── 内部辅助 ────────────────────────────────────────────────── */

type SetFn = (fn: (s: RecognizeState) => Partial<RecognizeState>) => void
type GetFn = () => RecognizeState

function patchItem(set: SetFn, get: GetFn, uid: string, patch: Partial<QueueItem>): void {
  const exists = get().items.some((i) => i.uid === uid)
  if (!exists) return // 期间被用户移除，安全忽略
  set((s) => ({
    items: s.items.map((i) => (i.uid === uid ? { ...i, ...patch } : i)),
  }))
}

/**
 * 并发池。最多同时跑 `limit` 个任务，其余排队。
 * D9 §10.7 自检项要求：**不得**用 `Promise.all` 全量并发。
 */
async function runPool<T>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<void>,
): Promise<void> {
  let cursor = 0
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (cursor < items.length) {
      const idx = cursor++
      await worker(items[idx]!)
    }
  })
  await Promise.all(runners)
}
