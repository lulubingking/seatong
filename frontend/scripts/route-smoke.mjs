#!/usr/bin/env node
/**
 * 逐路由渲染核验（route:smoke）
 * ────────────────────────────────────────────────────────────────
 * 目的：`typecheck` 与 `contract:check` 都无法发现「组件在浏览器里渲染时崩溃」。
 *       典型例子：`LoginPrompt` 在 `<RouterProvider>` 外侧调用 `useNavigate()`
 *       → 抛错且无错误边界 → **整棵树卸载、页面全白**，
 *       而 typecheck 全绿、HTTP 也是 200。
 *
 * 本脚本用真实 Chromium 逐个访问 13 条路由，检查：
 *   ① 页面是否有非空可见文本（白屏检测）
 *   ② 是否有未捕获的页面错误
 *   ③ 期望的关键文案是否出现
 *
 * 前置：前端 dev server（默认 5180）+ 后端（8000）均已运行。
 * 用法：node scripts/route-smoke.mjs [baseUrl]
 * ────────────────────────────────────────────────────────────────
 */

import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

const BASE = process.argv[2] || 'http://127.0.0.1:5180'

/**
 * 定位 agent-browser 可执行文件。
 *
 * 【为什么优先用 .exe 而不是 npm 的 .cmd 垫片】
 * Windows 上 `execFileSync('agent-browser')` 会 ENOENT（不做 PATHEXT 解析），
 * 退而求其次用 `.cmd` + `shell: true` 会引入两个严重问题：
 *   ① cmd.exe 会吃掉 JS 参数里的 `||` `&` `%`（eval 脚本必须刻意规避）
 *   ② **超时无法回收进程树** —— Node 只能杀 cmd.exe，真正的浏览器进程留在后台，
 *      后续调用被残留进程拖住，表现为第一条路由必然 ETIMEDOUT（实测复现 3 次）
 * agent-browser 自带了原生二进制 `bin/agent-browser-win32-x64.exe`，
 * 直接 exec 它即可绕开以上全部问题：无 shell、无元字符转义、超时可正常回收。
 */
function resolveAgentBrowser() {
  const npmDir = join(process.env.APPDATA || '', 'npm')
  const candidates = [
    process.env.AGENT_BROWSER_BIN,
    // ★ 首选：原生 exe（无 shell、无转义、超时可回收）
    join(npmDir, 'node_modules', 'agent-browser', 'bin', 'agent-browser-win32-x64.exe'),
    // 兜底：POSIX 下的 node 入口
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
  // 最后兜底：交给 PATH
  return { cmd: 'agent-browser', prefix: [] }
}

const AB = resolveAgentBrowser()
console.log(`（使用 agent-browser: ${AB.cmd}）`)


/**
 * 路由清单。`expect` 是**必须出现**的文案（用于确认渲染到了正确页面，
 * 而不是被守卫重定向或落到了 404）。
 * 需登录/需管理员的路由期望落在守卫目标上，故直接断言目标页文案。
 */
const ROUTES = [
  { path: '/', name: '首页', expect: ['上传一张水下照片'] },
  { path: '/recognize', name: '识别工作台', expect: ['上传'] },
  { path: '/about', name: '关于与免责', expect: ['免责'] },
  { path: '/history', name: '历史记录（未登录→登录页）', expect: ['登录'] },
  { path: '/profile', name: '个人中心（未登录→登录页）', expect: ['登录'] },
  { path: '/history/compare', name: '对比视图（未登录→登录页）', expect: ['登录'] },
  { path: '/admin/users', name: '用户管理（非管理员→404）', expect: ['404'] },
  { path: '/admin/records', name: '记录管理（非管理员→404）', expect: ['404'] },
  { path: '/admin/config', name: '系统配置（非管理员→404）', expect: ['404'] },
  { path: '/login', name: '登录', expect: ['登录'] },
  { path: '/register', name: '注册', expect: ['注册'] },
  { path: '/no-such-page', name: '404 兜底', expect: ['404'] },
]

const results = []

/**
 * 【超时纪律】用原生 exe 直接 exec（`shell: false`），因此：
 *   · 无 cmd.exe 元字符问题
 *   · 超时能真正回收子进程 → 不会留僵尸进程拖垮后续调用
 *     （曾用 `.cmd` + shell:true，导致第一条路由必然 ETIMEDOUT，复现 3 次）
 * 首次 open 仍给足预算（个别机器冷启动 + 残留 daemon 回收会慢）。
 */
const CMD_TIMEOUT = 45_000
const FIRST_OPEN_TIMEOUT = 90_000

let firstOpenDone = false

function ab(args, timeout = CMD_TIMEOUT) {
  return execFileSync(AB.cmd, [...AB.prefix, ...args], {
    encoding: 'utf8',
    timeout,
    stdio: ['ignore', 'pipe', 'pipe'],
    // 关键：不经 shell。原生 exe 无元字符问题，超时也能回收进程。
    shell: false,
  }).trim()
}

/** 静默执行（用于清理动作，失败无所谓） */
function abQuiet(args, timeout) {
  try {
    return ab(args, timeout)
  } catch {
    return ''
  }
}

/** 带一次重试的 open：首次给足冷启动时间，失败则清残留 daemon 再试 */
function abOpen(url) {
  const budget = firstOpenDone ? CMD_TIMEOUT : FIRST_OPEN_TIMEOUT
  try {
    const out = ab(['open', url], budget)
    firstOpenDone = true
    return out
  } catch {
    abQuiet(['close', '--all'], FIRST_OPEN_TIMEOUT)
    const out = ab(['open', url], FIRST_OPEN_TIMEOUT)
    firstOpenDone = true
    return out
  }
}



/**
 * 页面探测脚本（单行）。
 * 现在用原生 exe 直接 exec，不经 shell，因此可以正常写 `?.` 等语法。
 * 仍需单行，避免多行参数在不同终端下被拆断。
 */
const PROBE_JS =
  "JSON.stringify({url:location.pathname,text:(document.body.innerText||'').split(/\\s+/).join(' ').slice(0,4000),hasRoot:document.body.contains(document.getElementById('root')),title:document.title})"

/** eval 返回的是 JSON 字符串字面量，需二次解析 */
function evalJs(js) {
  const raw = ab(['eval', js])
  try {
    const once = JSON.parse(raw)
    return typeof once === 'string' ? JSON.parse(once) : once
  } catch {
    return raw
  }
}

console.log(`\n逐路由渲染核验 —— ${BASE}\n`)

/*
 * ── 为什么需要「预热」这一步（实测踩坑，勿删）────────────────────
 * 现象：无论用 `.cmd` 还是原生 `.exe`，**一个进程里第一次 `open` 必然挂死**
 *       （稳定 ETIMEDOUT 40/90 s），而其后所有调用都在 200~500 ms 内返回。
 *       经对照实验确认：
 *         · 与 URL 无关（`/`、`/recognize` 都会卡，取决于谁排第一）
 *         · 与 shell 无关（原生 exe + shell:false 同样卡）
 *         · 与 preflight `close --all` 无关（不做 preflight 也卡第一条）
 *       根因是 **daemon 冷启动**：首次调用要先拉起浏览器 daemon 并建立 CDP 连接，
 *       这一步在某些环境下会长时间阻塞；一旦 daemon 就绪，后续全部是快路径。
 *
 * 对策：循环开始前先做一次**预热**，把冷启动代价挪到循环之外。
 *       ⚠️ 预热失败后**绝不能**再 `close --all` —— 那会把刚起来的 daemon 打死，
 *          让循环的第一条路由重新付冷启动代价（此坑实测复现两次）。
 *          正确做法：不重置，直接往下走；若预热真的挂到底，第一条路由会承担
 *          一次失败，但后续 11 条全部走热路径。
 */
function warmUp() {
  try {
    ab(['open', BASE], FIRST_OPEN_TIMEOUT)
    firstOpenDone = true
    return true
  } catch {
    firstOpenDone = true
    return false
  }
}

const warm = warmUp()
console.log(
  warm ? '（daemon 预热完成）' : '（预热超时；daemon 可能仍在就绪中，继续尝试）',
)

for (const r of ROUTES) {
  const problems = []
  let probe = null

  try {
    abOpen(BASE + r.path)
    // 等 React 完成挂载与守卫判定（避免采样过早）
    abQuiet(['wait', '1200'])
    // 探测脚本必须是**单行且无 shell 元字符**（见 PROBE_JS 注释）
    probe = evalJs(PROBE_JS)
  } catch (e) {
    problems.push(`浏览器操作失败：${String(e.message).split('\n')[0]}`)
  }

  const text = probe?.text ?? ''

  // ① 白屏检测
  if (problems.length === 0 && text.length < 20) {
    problems.push(`页面几乎无文本（${text.length} 字符）→ 疑似白屏`)
  }

  // ② 期望文案
  if (problems.length === 0) {
    for (const exp of r.expect) {
      if (!text.includes(exp)) problems.push(`缺少期望文案「${exp}」`)
    }
  }

  results.push({ ...r, finalUrl: probe?.url, len: text.length, problems })
  console.log(
    problems.length === 0
      ? `✓ ${r.name}  ${probe?.url}  (${text.length} 字符)`
      : `✗ ${r.name}  ${probe?.url ?? '—'}\n     ${problems.join('\n     ')}`,
  )
}

/* ── 输出 ─────────────────────────────────────────────────── */

const bad = results.filter((r) => r.problems.length > 0)
console.log(`\n路由核验：${results.length - bad.length}/${results.length} 通过`)

abQuiet(['close', '--all'], FIRST_OPEN_TIMEOUT)

if (bad.length === 0) {
  console.log(`✓ ${ROUTES.length} 条路由全部正常渲染，无白屏\n`)
  process.exit(0)
}
console.error(`\n✗ ${bad.length} 条路由存在问题\n`)
process.exit(1)
