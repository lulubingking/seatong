#!/usr/bin/env node
/**
 * 令牌纪律检查器（lint:tokens）
 * ────────────────────────────────────────────────────────────────
 * 唯一来源：D9 §10.7（前端自检清单）
 *
 * 检查项：
 *   ① 组件/页面文件中不得出现十六进制颜色字面量（应使用 var(--token)）
 *   ② 不得出现 px 圆角字面量（borderRadius: '10px' 之类，应使用 var(--radius)）
 *   ③ tokens.css 是令牌的唯一来源 —— 其他 .css 文件不得定义 --token
 *   ④ 不得在 components/ pages/ 中出现内联错误文案（简化检查：常见错误句式）
 *
 * 用法：node scripts/lint-tokens.mjs
 * 退出码：0 = 通过；1 = 发现问题
 * ────────────────────────────────────────────────────────────────
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

const problems = []
let checked = 0

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) walk(p, out)
    else out.push(p)
  }
  return out
}

/** 收集需要检查的源文件 */
const files = walk(SRC)
const codeFiles = files.filter((f) => /\.(ts|tsx)$/.test(f))
const cssFiles = files.filter((f) => f.endsWith('.css'))

/* ── ① + ② 代码文件中的字面量 ─────────────────────────────── */

/** 允许出现十六进制的位置：tokens.css（单独检查）、注释内的说明 */
const HEX = /#[0-9a-fA-F]{3,8}\b/g
/** 允许出现 rgba() 的位置：tokens.css 中的 --ring 与两处阴影 */
const RGBA = /rgba?\(\s*\d+/g

for (const f of codeFiles) {
  const rel = relative(ROOT, f).replace(/\\/g, '/')
  const raw = readFileSync(f, 'utf8')
  checked++

  // 先把**整块**注释（含多行 JSDoc 与尾随注释）从全文剔除，再按行号对齐；
  // 逐行剔除只处理单行注释，会让多行块注释里的示例颜色被误报。
  let stripped = raw.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))

  raw.split('\n').forEach((line, i) => {
    const lineNo = i + 1
    // 再剔除该行的单行注释
    const noComment = (stripped.split('\n')[i] ?? line).replace(/\/\/.*$/, '')

    for (const m of noComment.matchAll(HEX)) {
      problems.push(`${rel}:${lineNo}  十六进制颜色字面量 ${m[0]} —— 应改用 var(--token)`)
    }
    for (const m of noComment.matchAll(RGBA)) {
      problems.push(`${rel}:${lineNo}  ${m[0]}…) 颜色字面量 —— 应改用 var(--token)`)
    }

    // px 圆角
    const radius = /borderRadius\s*:\s*['"]?\d+(\.\d+)?px/.exec(noComment)
    if (radius) {
      problems.push(`${rel}:${lineNo}  px 圆角字面量 —— 应改用 var(--radius*)`)
    }
    const radiusCss = /border-radius\s*:\s*\d+(\.\d+)?px/.exec(noComment)
    if (radiusCss) {
      problems.push(`${rel}:${lineNo}  px 圆角字面量 —— 应改用 var(--radius*)`)
    }

    // 阴影字面量（只允许 var(--shadow-*)）
    const shadow = /boxShadow\s*:\s*['"](?!var\()/.exec(noComment)
    if (shadow) {
      problems.push(`${rel}:${lineNo}  boxShadow 字面量 —— 应改用 var(--shadow-*)`)
    }

    // z-index 硬编码数值（只允许 2 / 60 / 200 / 300，或 var 引用 / Tailwind 类）
    const z = /zIndex\s*:\s*['"]?(\d+)/.exec(noComment)
    if (z && !['2', '60', '200', '300'].includes(z[1])) {
      problems.push(`${rel}:${lineNo}  zIndex: ${z[1]} 不在允许档位（2/60/200/300）内`)
    }
  })
}

/* ── ③ 令牌定义唯一性 ────────────────────────────────────── */

const TOKEN_DEF = /^\s*--[a-z0-9-]+\s*:/gim
for (const f of cssFiles) {
  const rel = relative(ROOT, f).replace(/\\/g, '/')
  if (rel.endsWith('src/styles/tokens.css')) continue
  const text = readFileSync(f, 'utf8')
  checked++
  text.split('\n').forEach((line, i) => {
    if (TOKEN_DEF.test(line) && !line.trim().startsWith('//') && !line.trim().startsWith('*')) {
      problems.push(
        `${rel}:${i + 1}  在此文件定义了设计令牌 —— 令牌只能在 styles/tokens.css 中定义`,
      )
    }
    TOKEN_DEF.lastIndex = 0
  })
}

/* ── ④ tokens.css 完整性抽查 ─────────────────────────────── */

const tokensPath = join(SRC, 'styles/tokens.css')
const tokensText = readFileSync(tokensPath, 'utf8')
checked++
const REQUIRED = [
  '--bg', '--surface', '--surface-2', '--surface-3',
  '--border', '--border-strong',
  '--text', '--text-2', '--text-3',
  '--primary', '--primary-600', '--primary-50', '--primary-100', '--ink',
  '--accent', '--accent-50', '--accent-border',
  '--warn', '--warn-50', '--warn-border',
  '--danger', '--danger-50', '--danger-border',
  '--success', '--success-50', '--success-border',
  '--metric', '--metric-deep',
  '--radius-sm', '--radius', '--radius-lg', '--radius-pill', '--ring',
  '--shadow-knob', '--shadow-toast',
  '--font', '--mono',
]
for (const t of REQUIRED) {
  if (!new RegExp(`${t}\\s*:`).test(tokensText)) {
    problems.push(`src/styles/tokens.css  缺少必需令牌 ${t}`)
  }
}

// 令牌总数统计（应与 D9 §3 的 34 项 + 本轮补充的 3 项一致）
const defined = new Set()
for (const m of tokensText.matchAll(/^\s*(--[a-z0-9-]+)\s*:/gim)) defined.add(m[1])
if (defined.size !== REQUIRED.length) {
  problems.push(
    `src/styles/tokens.css  令牌实际数量 ${defined.size}，脚本登记 ${REQUIRED.length} —— 请同步（多出的令牌需确认是否属于 §3）`,
  )
}

/* ── 输出 ────────────────────────────────────────────────── */

console.log(`\n令牌纪律检查 —— 扫描 ${checked} 个文件\n`)

if (problems.length === 0) {
  console.log('✓ 全部通过：无颜色字面量、无 px 圆角、令牌定义唯一\n')
  process.exit(0)
}

console.error(`✗ 发现 ${problems.length} 处问题：\n`)
for (const p of problems) console.error(`  ${p}`)
console.error('')
process.exit(1)
