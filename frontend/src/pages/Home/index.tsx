/**
 * 页面 1 · 首页 `/`（视图 `home`）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §5.1
 *
 * 需求锚点：FR-UPLOAD-01、FR-RESULT-05、NFR-SEC-01、NFR-COMPAT-02、NFR-PERF-01
 *
 * 布局骨架（§5.1）：
 *   ① Hero 区（标题 + 副标题 + 主 CTA）
 *   ② 三步流程说明（上传 → 识别 → 查看）
 *   ③ 能力说明卡（23 类覆盖 / 准确率 / 响应时间）
 *   ④ 免责提示条
 *
 * 状态与空态：本页**无空态**（纯静态内容 + 全站统计），
 * 唯一的动态数据是「识别服务状态」，见顶栏指示器。
 * ────────────────────────────────────────────────────────────────
 */

import { Link } from 'react-router-dom'
import { Button } from 'antd'
import { PATHS } from '@/routes/paths'
import { useAuthStore } from '@/stores/authStore'
import Card from '@/components/base/Card'
import Alert from '@/components/feedback/Alert'

export default function Home() {
  const guestQuota = useAuthStore((s) => s.guestQuota)
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn())

  return (
    <div className="flex flex-col gap-6">
      {/* ── ① Hero ────────────────────────────────────────── */}
      <section className="rounded-lg border border-line bg-surface px-6 py-10 sm:px-10 sm:py-14">
        <p className="m-0 mb-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-brand-50 text-brand text-[12.5px]">
          <span aria-hidden="true" className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--primary)' }} />
          基于 ResNet18 迁移学习 · 覆盖 23 个珊瑚礁鱼类类别
        </p>

        <h1 className="m-0 text-[26px] sm:text-[32px] font-semibold leading-[1.3] text-ink max-w-[620px]">
          上传一张水下照片，
          <br className="hidden sm:block" />
          认出这条鱼是什么
        </h1>

        <p className="m-0 mt-3.5 max-w-[560px] text-[14px] leading-[1.7] text-ink-2">
          面向水下摄影与海洋生态学习的鱼类识别工具。上传图片后返回物种名称、
          置信度与 Top-5 候选，并附上形态特征、生活习性与分布区域等参考信息。
        </p>

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <Link to={PATHS.recognize} className="no-underline">
            <Button type="primary" size="large">
              开始识别
            </Button>
          </Link>
          <Link to={PATHS.about} className="no-underline">
            <Button size="large">了解这个系统</Button>
          </Link>

          {!isLoggedIn && guestQuota && (
            <span className="text-[13px] text-ink-2 ml-1">
              免登录可试用 <b className="num text-brand">{guestQuota.remaining}</b> 次
            </span>
          )}
        </div>
      </section>

      {/* ── ② 三步流程 ────────────────────────────────────── */}
      <section>
        <h2 className="m-0 mb-4 text-[17px] font-semibold text-ink">怎么用</h2>
        <ol className="m-0 p-0 list-none grid gap-4 grid-cols-1 sm:grid-cols-3">
          <Step
            n={1}
            title="上传图片"
            desc="支持 JPG、PNG、BMP，单张不超过 10MB，一次最多 9 张。"
          />
          <Step
            n={2}
            title="等待识别"
            desc="模型对图片做归一化处理后推理，通常数百毫秒内完成。"
          />
          <Step
            n={3}
            title="查看结果"
            desc="获得首位物种判定与 Top-5 候选，以及该物种的形态与习性说明。"
          />
        </ol>
      </section>

      {/* ── ③ 能力说明 ────────────────────────────────────── */}
      <section>
        <h2 className="m-0 mb-4 text-[17px] font-semibold text-ink">覆盖范围与限制</h2>
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-3">
          <Capability
            value="23"
            unit="类"
            label="可识别的鱼类类别"
            desc="覆盖珊瑚礁常见小型鱼类，编号与图鉴一一对应。"
          />
          <Capability
            value="≥85"
            unit="%"
            label="测试集准确率目标"
            desc="以宏观 F1 为主要衡量指标，关注长尾类别的表现。"
          />
          <Capability
            value="≤3"
            unit="秒"
            label="单图端到端耗时"
            desc="从点击识别到结果呈现的完整链路耗时上限。"
          />
        </div>
      </section>

      {/* ── ④ 免责提示 ────────────────────────────────────── */}
      <Alert tone="info" title="识别结果仅供参考">
        本系统仅在上述 23 个类别范围内提供判定，对分布外物种无法给出有效结果，
        也无法替代专业分类学鉴定。请勿将结果直接用于科研论文或商业决策。
        <Link to={PATHS.about} className="ml-1 text-accent underline underline-offset-2">
          查看完整免责声明
        </Link>
      </Alert>

      {/* ── 登录引导（未登录时）───────────────────────────── */}
      {!isLoggedIn && (
        <Card
          title="登录后可以做什么"
          description="登录账号后解锁以下能力，游客试用次数不受影响。"
        >
          <ul className="m-0 p-0 list-none grid gap-2.5 grid-cols-1 sm:grid-cols-2">
            <Feature text="不限次数的图片识别" />
            <Feature text="自动保存识别历史，随时回看" />
            <Feature text="按物种筛选、按时间检索历史记录" />
            <Feature text="导出历史记录为 CSV 表格" />
          </ul>
          <div className="mt-4 flex gap-3">
            <Link to={PATHS.register} className="no-underline">
              <Button type="primary">注册账号</Button>
            </Link>
            <Link to={PATHS.login} className="no-underline">
              <Button>已有账号，去登录</Button>
            </Link>
          </div>
        </Card>
      )}
    </div>
  )
}

/* ── 局部组件 ────────────────────────────────────────────────── */

function Step({ n, title, desc }: { n: number; title: string; desc: string }) {
  return (
    <li className="rounded-lg border border-line bg-surface p-5">
      <span
        className="inline-flex items-center justify-center w-7 h-7 rounded-full text-[13px] font-semibold mb-3"
        style={{ background: 'var(--primary-50)', color: 'var(--primary-600)' }}
        aria-hidden="true"
      >
        {n}
      </span>
      <p className="m-0 text-[14.5px] font-semibold text-ink">{title}</p>
      <p className="m-0 mt-1.5 text-[13px] leading-[1.6] text-ink-2">{desc}</p>
    </li>
  )
}

function Capability({
  value,
  unit,
  label,
  desc,
}: {
  value: string
  unit: string
  label: string
  desc: string
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-5">
      <p className="m-0 flex items-baseline gap-0.5">
        <span className="text-[28px] font-semibold text-ink num">{value}</span>
        <span className="text-[14px] text-ink-2">{unit}</span>
      </p>
      <p className="m-0 mt-1.5 text-[13.5px] font-medium text-ink">{label}</p>
      <p className="m-0 mt-1 text-[12.5px] leading-[1.6] text-ink-2">{desc}</p>
    </div>
  )
}

function Feature({ text }: { text: string }) {
  return (
    <li className="flex items-start gap-2 text-[13.5px] text-ink-2 leading-[1.6]">
      <span aria-hidden="true" className="mt-[3px] shrink-0" style={{ color: 'var(--success)' }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
          <path
            d="M20 6.5 9.5 17 4 11.5"
            stroke="currentColor"
            strokeWidth="1.9"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      {text}
    </li>
  )
}
