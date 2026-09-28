/**
 * 页面 3 · 关于与免责 `/about`（视图 `about`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.3
 *
 * 需求锚点：FR-RESULT-05、NFR-SEC-01～05、NFR-COMPAT-01、NFR-PERF-02、BR-RECOG-01
 *
 * 布局骨架：
 *   ① 系统简介
 *   ② 技术实现（模型 / 数据集 / 性能）
 *   ③ 适用范围与已知限制（★ 重点，须诚实披露）
 *   ④ 数据处理与隐私说明（NFR-SEC 系列）
 *   ⑤ 免责声明（★ 法律性文案，须完整）
 * ────────────────────────────────────────────────────────────────
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Spin } from 'antd'
import Card from '@/components/base/Card'
import Alert from '@/components/feedback/Alert'
import * as configApi from '@/api/config'
import type { ModelInfo } from '@/api/types'
import { PATHS } from '@/routes/paths'

export default function About() {
  const [model, setModel] = useState<ModelInfo | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    configApi
      .getModelInfo()
      .then(setModel)
      .catch(() => setModel(null))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="m-0 text-[22px] font-semibold text-ink">关于海瞳鱼鉴</h1>
        <p className="m-0 mt-1.5 text-[13.5px] text-ink-2 leading-[1.7] max-w-[680px]">
          一个面向水下摄影爱好者与海洋生态学习者的鱼类图像识别工具。
          上传一张水下照片，系统会给出最可能的物种判定、置信度与候选排序，
          并附上该物种的形态、习性与分布资料。
        </p>
      </header>

      {/* ── ② 技术实现 ────────────────────────────────────── */}
      <Card title="技术实现">
        {loading ? (
          <div className="py-6 text-center">
            <Spin />
          </div>
        ) : (
          <dl className="m-0 grid gap-4 grid-cols-1 sm:grid-cols-2">
            <KV label="识别模型" value="ResNet18 迁移学习" />
            <KV label="分类类别数" value={model ? `${model.num_classes} 类` : '23 类'} />
            <KV label="输入尺寸" value={model ? `${model.img_size} × ${model.img_size}` : '224 × 224'} />
            <KV label="推理设备" value={model?.device === 'cuda' ? 'GPU 加速（CUDA）' : 'CPU'} />
            {model?.model_version && <KV label="模型版本" value={model.model_version} />}
            {model?.trained_metrics && (
              <KV
                label="验证集表现"
                value={`准确率 ${(model.trained_metrics.accuracy * 100).toFixed(1)}% · 宏观 F1 ${model.trained_metrics.macro_f1.toFixed(3)}`}
              />
            )}
          </dl>
        )}

        <Alert tone="info" className="mt-4">
          数据集来自公开的珊瑚礁鱼类图像库，共 23 个类别。各类别样本量差异较大，
          常见种与稀有种的数量相差可达三个数量级，这是本系统在稀有类别上表现
          较弱的根本原因。
        </Alert>
      </Card>

      {/* ── ③ 适用范围与已知限制（★ 诚实披露）─────────────── */}
      <Card title="适用范围与已知限制">
        <ul className="m-0 p-0 pl-4 list-disc flex flex-col gap-2 text-[13.5px] leading-[1.7] text-ink-2">
          <li>
            <b className="text-ink">仅覆盖 23 个类别</b>。超出这个范围的物种，系统仍会
            给出一个「最像」的结果，但该结果没有参考价值。若照片中的鱼不属于这 23 类，
            请勿采信系统输出。
          </li>
          <li>
            <b className="text-ink">对图片质量敏感</b>。水中光线不足、画面浑浊、
            鱼体被遮挡或只露出局部时，置信度会显著下降。
          </li>
          <li>
            <b className="text-ink">稀有类别可靠性较低</b>。部分类别仅有十余张训练样本，
            在这些类别上的判定需要更谨慎。
          </li>
          <li>
            <b className="text-ink">不识别个体、不计数、不测长</b>。系统只做「这条鱼
            属于哪个物种」的判断，不提供个体识别、鱼群计数或体长估算。
          </li>
          <li>
            <b className="text-ink">不做关注区域标注</b>。系统不会在图上框出它认为的
            关键部位 —— 这属于本系统明确的功能边界。
          </li>
        </ul>
      </Card>

      {/* ── ④ 数据处理与隐私 ──────────────────────────────── */}
      <Card title="数据处理与隐私">
        <ul className="m-0 p-0 pl-4 list-disc flex flex-col gap-2 text-[13.5px] leading-[1.7] text-ink-2">
          <li>上传的图片仅用于本次识别，不会用于模型训练或对外分享。</li>
          <li>原图有保留期限，超期后由系统自动清理；你也可随时在历史记录中主动删除。</li>
          <li>账号密码经加盐哈希后存储，系统不保存任何明文密码。</li>
          <li>游客试用不产生任何持久记录，仅以匿名会话标识统计剩余试用次数。</li>
          <li>生产环境应通过 HTTPS 访问，传输过程加密。</li>
        </ul>
      </Card>

      {/* ── ⑤ 免责声明 ────────────────────────────────────── */}
      <Card title="免责声明">
        <div className="text-[13.5px] leading-[1.8] text-ink-2 flex flex-col gap-3">
          <p className="m-0">
            本系统提供的物种识别结果由机器学习模型自动生成，
            <b className="text-ink">仅供学习、交流与初步参考之用</b>，
            不构成任何形式的专业鉴定结论。
          </p>
          <p className="m-0">
            系统无法保证识别结果的准确性、完整性或时效性。对于因采信本系统输出而
            产生的任何直接或间接损失，开发者与运营方不承担责任。
          </p>
          <p className="m-0">
            涉及科研论文、物种名录登记、生态调查、渔业管理、教学考核等需要权威结论的场景，
            请以专业分类学家的鉴定或权威图鉴为准。
          </p>
          <p className="m-0">
            使用者应自行确保所上传图片的合法来源，不得上传侵犯他人著作权、
            涉及个人隐私或违反法律法规的内容。
          </p>
        </div>
      </Card>

      <div className="flex flex-wrap gap-3">
        <Link to={PATHS.recognize} className="no-underline">
          <Button type="primary">开始识别</Button>
        </Link>
        <Link to={PATHS.home} className="no-underline">
          <Button>返回首页</Button>
        </Link>
      </div>
    </div>
  )
}

/* ── 局部组件 ────────────────────────────────────────────────── */

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="m-0 text-[12.5px] text-ink-3">{label}</dt>
      <dd className="m-0 mt-0.5 text-[14px] text-ink font-medium">{value}</dd>
    </div>
  )
}
