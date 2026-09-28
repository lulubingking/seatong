/**
 * 识别接口 —— `/api/recognize`、`/api/recognize/batch`（2 个端点）
 * 以及结果候选 `/api/results/{record_id}/candidates`
 *
 * 【额度语义】
 *   · 成功返回后扣减 1 次（登录用户不限次，游客限 3 次）
 *   · 仅业务码 `50002`（识别失败）**不扣额度**，可原图重试
 *   · 其余错误后须主动重新拉取额度（D9 §7.3.6 纪律 3）
 */

import { http } from './client'
import { ENDPOINTS } from './index'
import { TIMEOUT_RECOGNIZE } from '@/constants/limits'
import type {
  BatchRecognizeIn,
  BatchRecognizeOut,
  Candidate,
  RecognizeIn,
  RecognizeOut,
} from './types'

/** POST /api/recognize —— 单张识别 */
export function recognize(body: RecognizeIn): Promise<RecognizeOut> {
  return http.post<RecognizeOut>(ENDPOINTS.recognize, body, { timeout: TIMEOUT_RECOGNIZE })
}

/**
 * POST /api/recognize/batch —— 批量识别（顺序执行）
 *
 * 语义（后端实现约定）：
 *   · 逐张串行：单实例 + 8 GB 显存，并发会 OOM
 *   · 逐张扣额度；中途耗尽时**已成功的结果保留**，不整批回滚
 *   · 单张失败不中断整批，失败项在 `results[i].code` 中体现
 *   · 全批失败 HTTP 仍为 200，须按每项 `code` 判定
 */
export function recognizeBatch(body: BatchRecognizeIn): Promise<BatchRecognizeOut> {
  return http.post<BatchRecognizeOut>(ENDPOINTS.recognizeBatch, body, {
    timeout: TIMEOUT_RECOGNIZE * 3, // 批量按张数放宽（≤9 张）
  })
}

/** GET /api/results/{record_id}/candidates —— 取某条记录的 Top-K 候选 */
export function getCandidates(recordId: string): Promise<Candidate[]> {
  return http.get<Candidate[]>(ENDPOINTS.candidates(recordId))
}
