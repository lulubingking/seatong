/**
 * 物种接口 —— `/api/species*`（2 个端点，D8 §8.1～8.2）
 *
 * 【纪律（D9 §9.2.1）】前端**不得**硬编码 `class_index → 物种名` 映射。
 * 所有物种信息一律由接口下发。`speciesStore` 在应用启动后懒加载一次并内存缓存
 * （不写 localStorage，避免数据陈旧）。
 */

import { http } from './client'
import { ENDPOINTS } from './index'
import type { Species, SpeciesListOut } from './types'

/** GET /api/species —— 全部 23 类 */
export function listSpecies(): Promise<SpeciesListOut> {
  return http.get<SpeciesListOut>(ENDPOINTS.species)
}

/**
 * GET /api/species/{species_id} —— 单个物种详情
 *
 * 【路径参数名（勿改）】契约层参数名是 **`species_id`**（D8 §8.2），
 * 其**取值即 `class_index`（0–22）**。两者不是同一概念：
 * `species_id` 是对外契约的参数名，`class_index` 是数据库字段名与三方对齐键。
 * 之所以不改数据库字段名：它是模型输出 / species 表 / 知识库三处的唯一对齐键，
 * 改名会波及 D7、训练脚本与后端多处；而对外参数名属契约层，改动零成本。
 */
export function getSpecies(speciesId: number): Promise<Species> {
  return http.get<Species>(ENDPOINTS.speciesById(speciesId))
}
