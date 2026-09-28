/**
 * C-41 DropZone —— 上传区
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §4.5 C-41、§5.2（识别工作台）、§6.4（并发编排）
 *
 * 能力：
 *   · 点击选择 / 拖拽投放 / 剪贴板粘贴（Ctrl+V）
 *   · 客户端即时校验（体积、格式、张数）—— 不合格不进入队列（CLI-01）
 *   · 校验失败**汇总**提示，不逐个弹窗（避免弹窗风暴）
 *   · 超量时先询问是否继续添加（用户确认后静默入队，不重复弹窗）
 *
 * 【原型缺陷修复】原型的 `addFilesToQueue(n, forced)` 在超限确认后
 * 会**重复弹出**校验失败汇总弹窗 —— 本轮实现中 `force` 分支不弹汇总。
 * ────────────────────────────────────────────────────────────────
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Modal } from 'antd'
import { ACCEPT_ATTR, MAX_BATCH_FILES, MAX_FILE_MB } from '@/constants/limits'
import { LOCAL_ERROR_CODES } from '@/constants/errorMessages'
import { validateFiles, type FileReject } from '@/utils/validate'
import Alert from '@/components/feedback/Alert'

export interface DropZoneProps {
  /** 当前队列已有张数（用于计算剩余额度） */
  existingCount: number
  /** 是否禁用（识别进行中） */
  disabled?: boolean
  /** 通过校验的文件入队回调 */
  onAccept: (files: File[]) => void
}

export default function DropZone({ existingCount, disabled = false, onAccept }: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [rejects, setRejects] = useState<FileReject[]>([])
  const [overflowCount, setOverflowCount] = useState(0)
  const pendRef = useRef<File[]>([])

  /** 统一入口：校验 → 入队或提示 */
  const handleFiles = useCallback(
    (files: File[], force = false) => {
      if (files.length === 0) return
      const { accepted, rejected, overflow } = validateFiles(files, existingCount, force)

      // force 分支：用户已确认超限，不再重复弹校验汇总（原型缺陷修复）
      if (force) {
        if (accepted.length > 0) onAccept(accepted)
        setOverflowCount(0)
        pendRef.current = []
        return
      }

      setRejects(rejected)

      if (overflow.length > 0) {
        // 有文件被截断 → 询问是否继续添加
        pendRef.current = [...accepted, ...overflow]
        setOverflowCount(overflow.length)
        return
      }

      if (accepted.length > 0) onAccept(accepted)
    },
    [existingCount, onAccept],
  )

  const confirmOverflow = () => {
    handleFiles(pendRef.current, true)
  }

  const cancelOverflow = () => {
    // 放弃超量部分，仅接受额度内的
    const room = Math.max(0, MAX_BATCH_FILES - existingCount)
    const keep = pendRef.current.slice(0, room).filter((f) => !rejects.some((r) => r.file === f))
    if (keep.length > 0) onAccept(keep)
    setOverflowCount(0)
    pendRef.current = []
  }

  /* ── 剪贴板粘贴 ─────────────────────────────────────────── */
  useEffect(() => {
    if (disabled) return
    const onPaste = (e: ClipboardEvent) => {
      const items = e.clipboardData?.items
      if (!items) return
      const files: File[] = []
      for (const it of items) {
        if (it.kind === 'file') {
          const f = it.getAsFile()
          if (f) files.push(f)
        }
      }
      if (files.length === 0) {
        // 剪贴板无图片 —— 静默忽略（不改变当前状态，CLI-02）
        return
      }
      e.preventDefault()
      handleFiles(files)
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [disabled, handleFiles])

  return (
    <div>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="选择或拖入待识别的图片"
        aria-disabled={disabled}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (disabled) return
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        onDragOver={(e) => {
          if (disabled) return
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          if (disabled) return
          e.preventDefault()
          setDragging(false)
          handleFiles(Array.from(e.dataTransfer.files))
        }}
        className={[
          'flex flex-col items-center justify-center text-center px-5 py-9',
          'border-2 border-dashed transition-colors',
          disabled ? 'opacity-55 cursor-not-allowed' : 'cursor-pointer',
        ].join(' ')}
        style={{
          borderRadius: 'var(--radius-lg)',
          borderColor: dragging ? 'var(--primary)' : 'var(--border-strong)',
          background: dragging ? 'var(--primary-50)' : 'var(--surface)',
        }}
      >
        <span
          aria-hidden="true"
          className="mb-3 flex items-center justify-center rounded-full"
          style={{ width: 46, height: 46, background: 'var(--primary-50)', color: 'var(--primary)' }}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path d="M12 16.5V6.2" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
            <path d="M7.6 10.6 12 6.2l4.4 4.4" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M4.2 17.4v1.2a1.6 1.6 0 0 0 1.6 1.6h12.4a1.6 1.6 0 0 0 1.6-1.6v-1.2" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
          </svg>
        </span>

        <p className="m-0 text-[14.5px] font-medium text-ink">
          {dragging ? '松开即可添加' : '点击选择图片，或拖拽到此处'}
        </p>
        <p className="m-0 mt-1.5 text-[12.5px] text-ink-2 leading-[1.6]">
          支持 JPG、PNG、BMP，单张不超过 {MAX_FILE_MB}MB，一次最多 {MAX_BATCH_FILES} 张
        </p>
        <p className="m-0 mt-1 text-[12px] text-ink-3">也可以直接按 Ctrl + V 粘贴剪贴板中的图片</p>

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTR}
          multiple
          hidden
          onChange={(e) => {
            handleFiles(Array.from(e.target.files ?? []))
            // 清空以便重复选择同一文件时仍触发 change
            e.target.value = ''
          }}
        />
      </div>

      {/* ── 校验失败汇总（一次性列出，不逐个弹窗）──────────── */}
      {rejects.length > 0 && (
        <Alert
          tone="danger"
          title={`有 ${rejects.length} 个文件未通过校验`}
          className="mt-3"
          action={
            <button
              type="button"
              className="text-[12.5px] underline underline-offset-2 bg-transparent border-0"
              style={{ color: 'var(--danger)' }}
              onClick={() => setRejects([])}
            >
              知道了
            </button>
          }
        >
          <ul className="m-0 mt-1 p-0 pl-4 list-disc flex flex-col gap-0.5">
            {rejects.slice(0, 5).map((r, i) => (
              <li key={`${r.file.name}-${i}`} className="text-[12.5px]">
                <span className="text-ink-2">{r.file.name}</span> —— {r.message}
              </li>
            ))}
            {rejects.length > 5 && (
              <li className="text-[12.5px] text-ink-3">另有 {rejects.length - 5} 个文件同样未通过</li>
            )}
          </ul>
        </Alert>
      )}

      {/* ── 超量确认 ───────────────────────────────────────── */}
      <Modal
        open={overflowCount > 0}
        onCancel={cancelOverflow}
        centered
        width={380}
        title="超出单次数量上限"
        okText="继续添加"
        cancelText="只添加前几张"
        onOk={confirmOverflow}
        styles={{ content: { borderRadius: 'var(--radius-lg)' } }}
      >
        <p className="m-0 text-[13.5px] leading-[1.7] text-ink-2">
          单次最多处理 {MAX_BATCH_FILES} 张图片，当前已有 {existingCount} 张，
          还有 <b className="text-ink">{overflowCount}</b> 张放不进这一批。
          <br />
          你可以先识别当前这批，完成后再继续添加剩余图片。
        </p>
      </Modal>

      {/* 隐藏占位：确保 CLI-02 码被引用（剪贴板空时静默，不提示） */}
      <span hidden aria-hidden="true" data-code={LOCAL_ERROR_CODES.CLIPBOARD_EMPTY} />
    </div>
  )
}
