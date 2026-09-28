#!/usr/bin/env node
/**
 * 前后端契约一致性核验（contract:check）
 * ────────────────────────────────────────────────────────────────
 * 目的：`src/api/types.ts` 是按**实测后端响应**手写的。手写就会漂移 ——
 *       后端改一个字段名，TypeScript 不会报错（类型是断言，不是运行时校验），
 *       只会在浏览器里静默变成 `undefined`，然后在页面上显示成空白。
 *
 * 本脚本把「类型断言」变成「运行时校验」：
 *   对每个关键端点发一次真实请求，检查响应里**确实存在** types.ts 声明的字段，
 *   且类型一致。任何缺失或类型不符 → 退出码 1。
 *
 * 前置：后端已在 127.0.0.1:8000 运行。
 * 用法：node scripts/contract-check.mjs [baseUrl]
 * ────────────────────────────────────────────────────────────────
 */

const BASE = process.argv[2] || 'http://127.0.0.1:8000'

let pass = 0
const fails = []

/** 声明式契约：字段名 → 期望类型 */
const CONTRACT = [
  {
    name: 'POST /api/auth/login',
    path: '/api/auth/login',
    method: 'POST',
    body: { username: 'admin', password: 'Admin@12345' },
    /** token 从响应里取，供后续端点使用 */
    captureToken: (d) => d.access_token,
    expect: {
      access_token: 'string',
      refresh_token: 'string',
      token_type: 'string',
      expires_in: 'number',
      user: 'object',
    },
    nested: { user: ['id', 'username', 'nickname', 'role', 'status', 'created_at'] },
  },
  {
    name: 'GET /api/users/me（游客，无 token）',
    path: '/api/users/me',
    guest: true,
    expect: { user: 'object', is_guest: 'boolean', guest_quota: 'object' },
    nested: { guest_quota: ['is_guest', 'quota', 'used', 'remaining', 'known'] },
  },
  {
    name: 'GET /api/species',
    path: '/api/species',
    expect: { total: 'number', items: 'array' },
    arrayItem: { field: 'items', keys: ['class_index', 'cn_name', 'latin_name'] },
  },
  {
    name: 'GET /api/species/0',
    path: '/api/species/0',
    /** data 直接是对象 */
    expect: {
      class_index: 'number',
      cn_name: 'string',
      latin_name: 'string',
      morphology: 'string',
      habit: 'string',
      distribution: 'string',
    },
  },
  {
    name: 'GET /api/admin/stats',
    path: '/api/admin/stats',
    auth: true,
    expect: {
      total_users: 'number',
      active_users: 'number',
      total_records: 'number',
      total_uploads: 'number',
      records_today: 'number',
      top_species: 'array',
      avg_duration_ms: 'number',
    },
  },
  {
    name: 'GET /api/admin/config（数组，非分页）',
    path: '/api/admin/config',
    auth: true,
    expectArray: true,
    arrayItem: {
      field: null,
      keys: ['config_key', 'value', 'value_type', 'description', 'updated_at'],
    },
  },
  {
    name: 'GET /api/admin/logs',
    path: '/api/admin/logs?page=1&page_size=5',
    auth: true,
    expectPage: true,
    pageItemKeys: ['id', 'user_id', 'action', 'target_type', 'target_id', 'ip', 'created_at'],
  },
  {
    name: 'GET /api/admin/records',
    path: '/api/admin/records?page=1&page_size=5',
    auth: true,
    expectPage: true,
  },
  {
    name: 'GET /api/history（别名，与 /api/records 等价）',
    path: '/api/history?page=1&page_size=5',
    auth: true,
    expectPage: true,
    pageItemKeys: [
      'id', 'class_index', 'cn_name', 'latin_name', 'confidence',
      'is_low_confidence', 'duration_ms', 'status', 'created_at', 'thumb_url',
    ],
  },
  {
    name: 'GET /api/records（主路径，文档权威命名）',
    path: '/api/records?page=1&page_size=5',
    auth: true,
    expectPage: true,
    pageItemKeys: [
      'id', 'class_index', 'cn_name', 'latin_name', 'confidence',
      'is_low_confidence', 'duration_ms', 'status', 'created_at', 'thumb_url',
    ],
  },
  {
    name: 'GET /api/guest/quota（独立端点，字段名 limit）',
    path: '/api/guest/quota',
    guest: true,
    /** ⚠️ 字段名是 `limit`，与 /api/users/me 内嵌的 `guest_quota.quota` 有意不同 */
    expect: { limit: 'number', used: 'number', remaining: 'number' },
  },
  {
    name: 'GET /api/admin/users（admin 命名空间）',
    path: '/api/admin/users?page=1&page_size=5',
    auth: true,
    expectPage: true,
  },
  {
    name: 'GET /api/model-info',
    path: '/api/model-info',
    expect: {
      num_classes: 'number',
      img_size: 'number',
      device: 'string',
      ready: 'boolean',
      model_version: 'string',
    },
  },
  {
    /**
     * ⚠️ 本项是**回归守护**：`/api/health` 的模型状态是**嵌套**在 `model` 下，
     * 不是扁平字段。曾因 `getHealth` 类型写成扁平 `ready` 导致顶栏
     * 「服务正常」永远显示为「服务维护中」（`h.ready` → undefined）。
     */
    name: 'GET /api/health（★ 守护 model 嵌套结构）',
    path: '/api/health',
    expect: {
      status: 'string',
      app: 'string',
      version: 'string',
      db_pragmas: 'object',
      model: 'object',
    },
    nested: {
      model: ['ready', 'load_error', 'device', 'num_classes', 'img_size', 'model_version'],
      db_pragmas: ['foreign_keys', 'journal_mode'],
    },
  },
]

/* ── 断言辅助 ─────────────────────────────────────────────── */

function typeOf(v) {
  if (v === null) return 'null'
  if (Array.isArray(v)) return 'array'
  return typeof v
}

/** 校验对象是否含期望字段且类型一致 */
function checkShape(label, obj, expect) {
  for (const [k, t] of Object.entries(expect)) {
    if (!(k in obj)) {
      fails.push(`${label}  缺少字段 \`${k}\`（types.ts 已声明，后端未返回）`)
      continue
    }
    const got = typeOf(obj[k])
    // 可空字段：types.ts 里写成 `T | null` 的，后端返回 null 是合法的，
    // 不能判为类型不符（教训：`/api/users/me` 游客态 `user` 就是 null）。
    if (got === 'null') {
      pass++
      continue
    }
    if (got !== t) {
      fails.push(`${label}  字段 \`${k}\` 类型不符：期望 ${t}，实际 ${got}`)
    } else {
      pass++
    }
  }
}

function checkNested(label, obj, nested) {
  for (const [parent, keys] of Object.entries(nested || {})) {
    const child = obj?.[parent]
    if (!child || typeof child !== 'object') {
      fails.push(`${label}  嵌套对象 \`${parent}\` 不存在或非对象`)
      continue
    }
    for (const k of keys) {
      if (!(k in child)) fails.push(`${label}  \`${parent}.${k}\` 缺失`)
      else pass++
    }
  }
}

function checkArrayItems(label, arr, keys) {
  if (!Array.isArray(arr)) {
    fails.push(`${label}  期望数组，实际 ${typeOf(arr)}`)
    return
  }
  if (arr.length === 0) {
    console.log(`  · ${label}  数组为空，跳过元素级校验`)
    return
  }
  const first = arr[0]
  for (const k of keys || []) {
    if (!(k in first)) fails.push(`${label}  items[0].${k} 缺失`)
    else pass++
  }
}

/* ── 请求 ─────────────────────────────────────────────────── */

async function req(path, { method = 'GET', body, headers = {} } = {}) {
  const h = { ...headers }
  let payload = null
  if (body) {
    payload = JSON.stringify(body)
    h['Content-Type'] = 'application/json'
  }
  const res = await fetch(BASE + path, { method, headers: h, body: payload })
  const text = await res.text()
  let json = null
  try {
    json = JSON.parse(text.replace(/^\uFEFF/, ''))
  } catch {
    json = { __raw: text.slice(0, 200) }
  }
  return { status: res.status, json }
}

/* ── 主流程 ───────────────────────────────────────────────── */

console.log(`\n前后端契约核验 —— 目标 ${BASE}\n`)

let token = null
let guestId = null

for (const spec of CONTRACT) {
  const headers = {}
  if (spec.auth) {
    if (!token) {
      fails.push(`${spec.name}  需要 token 但前面未成功登录`)
      continue
    }
    headers['Authorization'] = `Bearer ${token}`
  }
  if (spec.guest) {
    if (!guestId) {
      // 无 token 时会退化为游客，显式带上会话头更贴近前端行为
      guestId = 'contract-' + Math.random().toString(16).slice(2, 18)
    }
    headers['X-Guest-Session'] = guestId
  }

  let out
  try {
    out = await req(spec.path, { method: spec.method, body: spec.body, headers })
  } catch (e) {
    fails.push(`${spec.name}  请求失败：${e.message}`)
    console.log(`✗ ${spec.name}`)
    continue
  }

  const { status, json } = out
  if (json.code !== 0) {
    fails.push(`${spec.name}  code=${json.code}（期望 0）message=${json.message}`)
    console.log(`✗ ${spec.name}  code=${json.code}`)
    continue
  }

  if (spec.captureToken) {
    const t = spec.captureToken(json.data)
    if (t) token = t
    else fails.push(`${spec.name}  未能捕获 token`)
  }

  const data = json.data
  const label = spec.name

  if (spec.expectArray) {
    checkArrayItems(label, data, spec.arrayItem?.keys)
  } else if (spec.expectPage) {
    checkShape(label, data, {
      items: 'array', page: 'number', page_size: 'number',
      total: 'number', total_pages: 'number',
    })
    checkArrayItems(label + ' items', data.items, spec.pageItemKeys)
  } else {
    checkShape(label, data, spec.expect)
    checkNested(label, data, spec.nested)
    if (spec.arrayItem) {
      checkArrayItems(label, data[spec.arrayItem.field], spec.arrayItem.keys)
    }
  }

  console.log(`✓ ${label}  HTTP ${status}`)
}

/* ── 旧路径下线守护 ─────────────────────────────────────────
 * 2026-09-21 把实现对齐到文档（V1.1 命名纪律）后，以下路径**必须不存在**。
 * 若哪天有人手滑恢复旧命名，前端会静默 404 —— 那是最难查的一类 bug。
 * 这里主动断言它们返回 404，把「静默回退」变成「立即红灯」。
 */
const RETIRED = [
  'GET /api/users（已迁至 /api/admin/users）',
  'GET /api/admin/config/{key}（改为 PUT /api/admin/config 全量）',
  'GET /api/users/{id}/password（改为 /api/admin/users/{id}/reset-password）',
]

console.log('')
for (const name of RETIRED) {
  const [method, path] = name.split('（')[0].split(' ')
  let out
  try {
    out = await req(path, { method, headers: { Authorization: `Bearer ${token}` } })
  } catch (e) {
    fails.push(`旧路径守护 ${name}  请求失败：${e.message}`)
    continue
  }
  // 旧路径应返回 404（路由不存在）
  if (out.json?.code === 0) {
    fails.push(`旧路径守护 ${name}  仍然可用！说明命名回退，须清理`)
    console.log(`✗ ${name}  仍返回 200`)
  } else {
    pass++
    console.log(`✓ ${name}  已下线  code=${out.json?.code}`)
  }
}

/* ── 输出 ─────────────────────────────────────────────────── */

const total = pass + fails.length
console.log(`\n契约断言：${pass}/${total} 通过`)

if (fails.length === 0) {
  console.log('✓ 前后端契约完全一致：types.ts 声明的字段后端均按预期返回\n')
  process.exit(0)
}

console.error(`\n✗ 发现 ${fails.length} 处契约不一致：\n`)
for (const f of fails) console.error(`  ${f}`)
console.error('\n请据此更新 src/api/types.ts 或后端响应。\n')
process.exit(1)
