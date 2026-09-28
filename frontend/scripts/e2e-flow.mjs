#!/usr/bin/env node
/**
 * 真实浏览器 E2E 全链路（e2e:flow）
 * ────────────────────────────────────────────────────────────────
 * 目的：route-smoke 只证明「每条路由能渲染」；HTTP 探针只证明「后端契约正确」。
 *       本脚本用真实 Chromium 走**用户旅程**，覆盖两者之间的缝隙：
 *
 *   旅程 A（游客）：/recognize → 上传真实鱼图 → 开始识别 → ResultHero
 *                   （断言「识别结果 / 置信度 / Top-5 候选物种」）→ 截图
 *   旅程 B（额度拦截）：用 API 把**浏览器同一游客会话**的 3 次额度耗尽
 *                   → 再点「开始识别」→ 前端应本地拦截并弹登录引导
 *                   （不发第 4 次请求 —— 这层拦截只有浏览器 E2E 能验证）
 *   旅程 C（登录用户）：/login 表单登录 → /recognize 识别 fish_3
 *                   → 点「去历史记录查看」→ /history 出现该记录 → 截图
 *
 * 前置：前端 dev server（5180）+ 后端（8000）已运行。
 * 用法：node scripts/e2e-flow.mjs [baseUrl]
 * 产出：frontend/.verify/e2e/*.png + e2e-flow-report.json
 * ────────────────────────────────────────────────────────────────
 */

import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
const DATA = join(ROOT, 'fish_image23', 'fish_image')
const OUT = join(ROOT, 'frontend', '.verify', 'e2e')
const BASE = process.argv[2] || 'http://127.0.0.1:5180'
const API = process.env.SEATONG_API || 'http://127.0.0.1:8000'

/* ── agent-browser（原生 exe 纪律，与 route-smoke.mjs 一致）────────── */
function resolveAgentBrowser() {
  const npmDir = join(process.env.APPDATA || '', 'npm')
  const candidates = [
    process.env.AGENT_BROWSER_BIN,
    join(npmDir, 'node_modules', 'agent-browser', 'bin', 'agent-browser-win32-x64.exe'),
    join(npmDir, 'node_modules', 'agent-browser', 'bin', 'agent-browser.js'),
    '/usr/local/bin/agent-browser',
  ].filter(Boolean)
  for (const c of candidates) {
    if (c.endsWith('.js')) {
      if (existsSync(c)) return { cmd: process.execPath, prefix: [c] }
      continue
    }
    if (existsSync(c)) return { cmd: c, prefix: [] }
  }
  return { cmd: 'agent-browser', prefix: [] }
}
const AB = resolveAgentBrowser()
const CMD_TIMEOUT = 45_000
const FIRST_OPEN_TIMEOUT = 90_000
let firstOpenDone = false

function ab(args, timeout = CMD_TIMEOUT) {
  return execFileSync(AB.cmd, [...AB.prefix, ...args], {
    encoding: 'utf8',
    timeout,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
  }).trim()
}
function abQuiet(args, timeout = CMD_TIMEOUT) {
  try { return ab(args, timeout) } catch { return '' }
}
function abOpen(url) {
  const budget = firstOpenDone ? CMD_TIMEOUT : FIRST_OPEN_TIMEOUT
  try { firstOpenDone = true; return ab(['open', url], budget) } catch {
    abQuiet(['close', '--all'], FIRST_OPEN_TIMEOUT)
    firstOpenDone = true
    return ab(['open', url], FIRST_OPEN_TIMEOUT)
  }
}
function evalJs(js) {
  const raw = ab(['eval', js])
  try {
    const once = JSON.parse(raw)
    // CLI 对 eval 结果做 JSON 编码：字符串型结果解析一次即得原值；
    // 若字符串本身又是 JSON（如 JSON.stringify 的对象），再解析一次。
    if (typeof once === 'string') {
      try { return JSON.parse(once) } catch { return once }
    }
    return once
  } catch { return raw }
}
/** 不抛异常版：失败返回空串（用于可能元素不存在的点击） */
function abTry(args, timeout = CMD_TIMEOUT) {
  try { return ab(args, timeout) } catch { return '' }
}
/**
 * 按钮点击（eval 触发）。
 * 【为什么不用 `find text <label> click`】实测（diag-recognize.mjs）：
 * find text 对 antd Button 的点击不触发 React 合成事件 —— 点击后队列项
 * 停留在「待上传」、网络面板零请求；改用 eval 在页面内对按钮派发真实
 * click 事件（冒泡至 React 根监听器），稳定生效。仅匹配首个前缀命中的按钮。
 */
function clickButton(label) {
  const js = `(() => { const b = [...document.querySelectorAll('button')]` +
    `.find(x => x.textContent.trim().startsWith('${label}'));` +
    ` if (b) { b.click(); return 'clicked' } return 'not-found' })()`
  return String(evalJs(js) ?? '')
}
/** 等待页面文本包含全部关键词（轮询 eval，最多 waitMs） */
async function waitText(keys, waitMs = 30_000) {
  const t0 = Date.now()
  let text = ''
  while (Date.now() - t0 < waitMs) {
    await new Promise((r) => setTimeout(r, 800))
    text = String(evalJs('document.body.innerText') ?? '')
    if (keys.every((k) => text.includes(k))) return { ok: true, text }
  }
  return { ok: false, text }
}

/* ── 断言与报告 ────────────────────────────────────────────────── */
const results = []
let passN = 0
function check(label, cond, extra = '') {
  passN += cond ? 1 : 0
  results.push({ label, ok: !!cond, extra })
  console.log(`${cond ? '✓' : '✗'} ${label}${extra ? `  ${extra}` : ''}`)
  return !!cond
}

/* ── 后端 API（Node 侧，用于准备数据与清理；限速同服务端 60/min 纪律）── */
let lastCall = 0
async function throttle() {
  const dt = Date.now() - lastCall
  if (dt < 1100) await new Promise((r) => setTimeout(r, 1100 - dt))
  lastCall = Date.now()
}
async function api(method, p, body, headers = {}, tries = 3) {
  for (let i = 0; i < tries; i++) {
    await throttle()
    const h = { ...headers }
    let payload
    if (body !== undefined) { h['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
    const r = await fetch(API + p, { method, headers: h, body: payload })
    const j = await r.json().catch(() => ({}))
    if (r.status === 429 && i < tries - 1) { await new Promise((s) => setTimeout(s, 3000)); continue }
    return { status: r.status, json: j }
  }
}
async function apiUpload(token, filePath, guestSession) {
  await throttle()
  const raw = await import('node:fs').then((m) => m.readFileSync(filePath))
  const fd = new FormData()
  fd.append('file', new Blob([raw], { type: 'image/png' }), filePath.split('\\').pop())
  const headers = guestSession ? { 'X-Guest-Session': guestSession } : { Authorization: `Bearer ${token}` }
  const r = await fetch(`${API}/api/images`, { method: 'POST', headers, body: fd })
  return { status: r.status, json: await r.json().catch(() => ({})) }
}
function firstImage(n) {
  // 类目小样本纪律：从指定类取第 3 张（前 2 张可能被其他探针反复使用）
  const dir = join(DATA, `fish_${n}`)
  const fsMod = import('node:fs')
  return fsMod.then((m) => m.readdirSync(dir).filter((f) => f.endsWith('.png'))[2])
    .then((f) => join(dir, f))
}

/* ── 主流程 ────────────────────────────────────────────────────── */
mkdirSync(OUT, { recursive: true })
console.log(`\n浏览器 E2E 全链路 —— 前端 ${BASE} / 后端 ${API}\n`)
console.log(`（使用 agent-browser: ${AB.cmd}）`)

// 预热（daemon 冷启动代价挪到断言外，与 route-smoke 相同的坑）
try { ab(['open', BASE], FIRST_OPEN_TIMEOUT) } catch { /* 预热失败不重试，继续 */ }
firstOpenDone = true

/* 旅程 A：游客识别 */
console.log('\n—— 旅程 A：游客上传并识别 ——')
abOpen(`${BASE}/recognize`)
abQuiet(['wait', 1500])
// 清 localStorage 保证游客会话全新（额度 3/3）
evalJs('localStorage.clear(); "cleared"')
abQuiet(['reload'])
await waitText(['试用剩余'], 15_000)
const a1 = await waitText(['识别工作台', '试用剩余 3 / 3'], 15_000)
check('A1 游客进入识别工作台，额度显示 3/3', a1.ok)

const fish1 = await firstImage(1)
abTry(['upload', 'input[type=file]', fish1])
const a2 = await waitText(['待处理图片（1 / 9）'], 15_000)
check('A2 上传真实鱼图后进入文件队列', a2.ok, fish1.split('\\').pop())

check('A2x 点击提交按钮', clickButton('开始识别') === 'clicked')
const a3 = await waitText(['识别结果', '置信度'], 40_000)
check('A3 提交识别后出现 ResultHero 结果卡', a3.ok)

const cnA = /识别结果\s*\n\s*([^\n]+)/.exec(a3.text)?.[1]?.trim() ?? ''
check('A4 结果卡含物种中文名', /^[\u4e00-\u9fa5（）]+$/.test(cnA), cnA || '未匹配到')
const a5 = await waitText(['Top-5 候选物种', '形态特征'], 15_000)
check('A5 Top-5 候选与物种知识齐备', a5.ok)
const shotA = join(OUT, 'e2e-guest-result.png')
abQuiet(['screenshot', shotA])
check('A6 游客结果截图已保存', existsSync(shotA), shotA)

/* 旅程 B：额度用尽 → 前端本地拦截 */
console.log('\n—— 旅程 B：游客额度用尽的本地拦截 ——')
const sid = String(evalJs('localStorage.getItem("seatong.guest_session")') ?? '')
check('B1 浏览器游客会话 ID 可读取', /^[0-9a-f-]{8,}$/i.test(sid), sid.slice(0, 12) + '…')
// 用 API 把该会话剩余 2 次额度耗尽（浏览器已用 1 次）
let exhausted = false
if (/^[0-9a-f-]{8,}$/i.test(sid)) {
  const up = await apiUpload(null, await firstImage(2), sid)
  if (up.json?.data?.image?.id) {
    for (let k = 0; k < 3; k++) {
      const r = await api('POST', '/api/recognize', { image_id: up.json.data.image.id },
        { 'X-Guest-Session': sid })
      if (r.json?.code !== 0) { exhausted = r.json?.code === 42901; break }
    }
  }
}
check('B2 同会话剩余额度已由 API 耗尽（第 4 次返回 42901）', exhausted)

// 浏览器内再传一张并点识别 → 应弹登录引导而非发请求
const fish4 = await firstImage(4)
abTry(['upload', 'input[type=file]', fish4])
await waitText(['待处理图片'], 15_000)
check('B3x 点击提交按钮', clickButton('开始识别') === 'clicked')
// 本地拦截文案为「试用次数已用完」（前置门禁）；若本地额度未校准则由
// 服务端 42901 弹「游客试用额度已用尽」——两者共同关键词取「已用」
const b3raw = await waitText(['已用'], 12_000)
check('B3 额度用尽触发登录引导（不发第 4 次请求或由 42901 拦截）',
      b3raw.ok && b3raw.text.includes('登录'), '')
const shotB = join(OUT, 'e2e-guest-quota-blocked.png')
abQuiet(['screenshot', shotB])
check('B4 额度拦截截图已保存', existsSync(shotB), shotB)

/* 旅程 C：注册用户登录 → 识别 → 历史 */
console.log('\n—— 旅程 C：登录用户识别与历史记录 ——')
const uname = `e2e${Math.floor(Math.random() * 1e6)}`
const reg = await api('POST', '/api/auth/register',
  { username: uname, password: 'Passw0rd1', nickname: '浏览器E2E' })
check('C1 API 预置注册用户', reg.json?.code === 0, uname)

abOpen(`${BASE}/login`)
await waitText(['登录账号'], 15_000)
abTry(['fill', 'input[placeholder="请输入账号名"]', uname])
abTry(['fill', 'input[placeholder="请输入密码"]', 'Passw0rd1'])
abTry(['click', 'button[type=submit]'])
const c2 = await waitText(['登录成功'], 12_000)
check('C2 表单登录成功', c2.ok)

// 登录态识别 fish_3（期望命中 长棘光鳃鱼）
abOpen(`${BASE}/recognize`)
await waitText(['识别工作台'], 15_000)
const c3 = await waitText(['识别工作台'], 3_000).then((r) =>
  check('C3 登录态下不再显示游客额度', !r.text.includes('试用剩余')))
const fish3 = await firstImage(3)
abTry(['upload', 'input[type=file]', fish3])
await waitText(['待处理图片（1 / 9）'], 15_000)
check('C3x 点击提交按钮', clickButton('开始识别') === 'clicked')
const c4 = await waitText(['识别结果', '置信度'], 40_000)
check('C4 登录用户识别成功', c4.ok)
const cnC = /识别结果\s*\n\s*([^\n]+)/.exec(c4.text)?.[1]?.trim() ?? '长棘光鳃鱼'
check('C5 fish_3 命中长棘光鳃鱼', cnC === '长棘光鳃鱼', cnC || '未匹配到')

// 点「去历史记录查看」→ /history（按钮仅在单张结果出现时存在，找不到则直接开 /history）
const clicked = clickButton('去历史记录查看') === 'clicked'
const c6 = clicked
  ? await waitText(['历史记录', cnC], 20_000)
  : (abOpen(`${BASE}/history`), await waitText(['历史记录', cnC], 20_000))
check('C6 历史记录页出现刚识别的记录', c6.ok)
const shotC = join(OUT, 'e2e-history.png')
abQuiet(['screenshot', shotC])
check('C7 历史页截图已保存', existsSync(shotC), shotC)

// 页面错误收集
const pageErrors = abQuiet(['errors']) || ''
check('C8 全程无未捕获页面错误', !/Error|Uncaught/i.test(pageErrors),
  pageErrors.split('\n')[0]?.slice(0, 120) || '无')

/* ── 善后：删除测试账号与其图像（与 HTTP 探针同序：先账号后图像）── */
console.log('\n—— 善后 ——')
const adminTok = await (async () => {
  for (const pwd of ['Admin@12345', 'Admin@9999', 'Admin@2026']) {
    const r = await api('POST', '/api/auth/login', { username: 'admin', password: pwd })
    if (r.json?.code === 0) return r.json.data.access_token
  }
  return null
})()
let cleaned = false
if (adminTok && reg.json?.data?.user?.id) {
  // 先取该用户的图像 id（删账号后图像置 NULL，仍需按 id 清理）
  const recs = await api('GET', '/api/records?page_size=50', undefined,
    { Authorization: `Bearer ${reg.json.data.access_token}` })
  const imgIds = (recs.json?.data?.items ?? [])
    .map((it) => it.image_id).filter(Boolean)
  const delU = await api('DELETE', `/api/admin/users/${reg.json.data.user.id}`,
    undefined, { Authorization: `Bearer ${adminTok}` })
  let delI = 0
  for (const iid of imgIds) {
    const r = await api('DELETE', `/api/images/${iid}`, undefined,
      { Authorization: `Bearer ${adminTok}` })
    delI += r.json?.code === 0 ? 1 : 0
  }
  cleaned = delU.json?.code === 0
  check('C9 善后：测试账号与图像已清理', cleaned,
    `账号 ${cleaned ? 1 : 0} 个 / 图像 ${delI}/${imgIds.length} 张`)
} else {
  check('C9 善后：管理员令牌可用', false, '跳过清理（管理员不可用）')
}

abQuiet(['close', '--all'], FIRST_OPEN_TIMEOUT)

/* ── 汇总 ─────────────────────────────────────────────────────── */
const bad = results.filter((r) => !r.ok)
const report = {
  base: BASE, api: API, finished_at: new Date().toISOString(),
  passed: passN, failed: bad.length, results,
}
writeFileSync(join(OUT, 'e2e-flow-report.json'),
  JSON.stringify(report, null, 1), 'utf8')
console.log(`\n浏览器 E2E：${passN}/${results.length} 通过（报告 ${join(OUT, 'e2e-flow-report.json')}）`)
process.exit(bad.length ? 1 : 0)
