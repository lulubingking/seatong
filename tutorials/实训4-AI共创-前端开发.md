# 实训 4 基于 AI 共创的海瞳鱼鉴前端开发

## 一、实训目标

1. 了解基于 AI 共创的前端开发协作流程（三文档驱动：PRD / UIUX / 开发任务）。
2. 掌握 Vite + React + TypeScript 前端工程的搭建与依赖安装（AntD5 / Tailwind / Zustand / Axios）。
3. 能够依据真实代码理解并复现核心页面：识别工作台（DropZone 上传、ProbBarChart Top-5 概率图、历史记录）。
4. 掌握前端与 FastAPI 后端的联调要点（Axios baseURL、Vite 代理、CORS、统一响应体）。
5. 掌握 `npm run selfcheck` 自检流程（typecheck / lint:tokens / contract:check 118 / route:smoke 12）。

## 二、实训内容

### 1. 背景知识

- **AI 共创（文档驱动）**：本次前端不手写全部代码，而是向 AI 提供三份权威文档（产品需求规格说明书、界面设计文档、开发任务文档），由 AI 生成符合约束的前端工程，开发者负责核对、联调与自检。
- **Vite + React 18 + TypeScript**：构建工具 Vite 6，UI 框架 React 18，类型系统 TypeScript 5.6。开发服务器端口固定为 **5180**（非 Vite 默认 5173，因 5173 已被同机另一项目占用，`vite.config.ts` 中 `strictPort: true`）。
- **Ant Design 5 / Tailwind 3 / Zustand 5 / Axios 1.7**：组件库、原子化样式、轻量全局状态、统一 HTTP 客户端。
- **前后端契约**：接口以 `/api` 为前缀，后端端口 8000。开发期通过 Vite 代理 `/api → http://127.0.0.1:8000` 规避跨域。统一响应体 `{ code, message, data, request_id }`，`code=0` 成功。

### 2. 项目结构

```
frontend/
├── package.json                       # 依赖与 selfcheck 脚本
├── vite.config.ts                     # 端口 5180 / 代理 / @ 别名
├── scripts/{lint-tokens,contract-check,route-smoke}.mjs
└── src/
    ├── api/{client,index,types,images,recognize,records}.ts
    ├── components/domain/{DropZone,ProbBarChart,ResultHero}.tsx
    ├── constants/{enums,limits,errorMessages}.ts
    ├── pages/Recognize/index.tsx      # 识别工作台（视图 recognize）
    ├── pages/History/List.tsx         # 历史记录（视图 history）
    ├── stores/{recognizeStore,authStore,speciesStore}.ts
    ├── routes/paths.ts
    └── utils/{format,validate}.ts
```

## 三、实训步骤

### 步骤1：向 AI 提出前端开发需求（三文档驱动）

**操作内容：**
打开与 AI 的对话窗口，将以下需求原文粘贴发送（发送前确认 PRD、UIUX 设计文档、开发任务文档就位于 `E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\` 下相应目录）。

```text
你是一名资深前端工程师，请基于以下三份文档完成「海瞳鱼鉴」前端工程开发：
1. 产品需求规格说明书（PRD）—— 功能、错误码、联调口径
2. 界面设计文档（UIUX）—— 布局、设计令牌、组件清单
3. 开发任务文档 —— 页面拆分与实现要点

硬性技术约束：
- 技术栈：Vite 6 + React 18 + TypeScript 5.6 + Ant Design 5 + Tailwind 3 + Zustand 5 + Axios 1.7
- 开发服务器端口固定 5180（vite.config.ts 中 strictPort: true，不得改回 5173）
- 全部接口经 src/api/client.ts 的 Axios 实例；baseURL 用 import.meta.env.VITE_API_BASE，缺省为空
- API 前缀 /api；统一响应体 { code, message, data, request_id }，code=0 成功
- 错误码：40101 未认证、40401 他人资源、42902 限流、42901 游客额度耗尽
- 状态管理用 Zustand：识别作业状态机放 recognizeStore（单一 phase 字段驱动）
- 关键页面：识别工作台 /recognize（DropZone 上传 + ProbBarChart Top-5 概率图）、历史记录 /history
- 提供 selfcheck 脚本：typecheck / lint:tokens / contract:check（118 条）/ route:smoke（12 条）
```

**验证方法：**
```powershell
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\02.产品需求规格说明书\海瞳鱼鉴-PRD.md"
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\03.界面设计文档\海瞳鱼鉴-UIUX.md"
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\03.开发任务文档\海瞳鱼鉴-开发任务.md"
# 预期输出均为 True
```

**成功标志：**
- AI 已确认理解三文档并产出前端工程；关键文件 `src/api/client.ts`、`src/pages/Recognize/index.tsx`、`src/stores/recognizeStore.ts` 均存在。

### 步骤2：前端工程搭建（npm create vite → React + TS + 依赖）

**操作命令：**
```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend"
npm install antd@^5.22.2 axios@^1.7.9 react-router-dom@^6.28.0 zustand@^5.0.2
npm install -D @vitejs/plugin-react@^4.3.4 autoprefixer@^10.4.20 postcss@^8.4.49 tailwindcss@^3.4.17 typescript@~5.6.3 vite@^6.0.3 @types/node @types/react @types/react-dom
```

**验证方法：**
```powershell
npm ls vite antd tailwindcss zustand axios react react-router-dom 2>$null
# 预期：以上包均出现，版本与 package.json 一致
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend\package.json" | Select-String '"selfcheck"'
# 预期：命中 selfcheck 串联脚本定义
```

**成功标志：**
- `node_modules` 生成，依赖安装无致命报错；`package.json` 的 `scripts` 含 `dev / build / typecheck / selfcheck`。

```json
// frontend/package.json（真实 scripts 节选）
"scripts": {
  "dev": "vite",
  "build": "tsc -b && vite build",
  "typecheck": "tsc --noEmit",
  "lint:tokens": "node scripts/lint-tokens.mjs",
  "contract:check": "node scripts/contract-check.mjs",
  "route:smoke": "node scripts/route-smoke.mjs",
  "selfcheck": "npm run typecheck && npm run lint:tokens && npm run contract:check && npm run route:smoke"
}
```

### 步骤3：确认开发服务器端口与代理（vite.config.ts）

**操作内容：**
核对 `vite.config.ts`：开发服务器监听 `127.0.0.1:5180`、`strictPort: true`，并配置 `/api` 代理到后端 8000。

```ts
// frontend/vite.config.ts（真实片段）
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    host: '127.0.0.1',
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': {
        target: process.env.SEATONG_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
```

**验证方法：**
```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend\vite.config.ts" | Select-String 'port: 5180'
# 预期：命中 port: 5180
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend\vite.config.ts" | Select-String "target: process.env.SEATONG_API_TARGET"
# 预期：命中 /api 代理目标
```

**成功标志：**
- 文件明确 `port: 5180` 且存在 `/api` 代理配置，前后端联调无需在浏览器侧处理跨域。

### 步骤4：核心页面实现要点（DropZone 上传 / ProbBarChart 概率图 / 状态机）

**操作内容：**
识别工作台 `src/pages/Recognize/index.tsx` 渲染标题、额度提示、上传区、文件队列与结果区。上传区用 `DropZone`（点击 / 拖拽 / Ctrl+V，客户端即时校验）；结果区用 `ProbBarChart` 展示 Top-5。

```tsx
// frontend/src/pages/Recognize/index.tsx（真实片段）
import DropZone from '@/components/domain/DropZone'
import ProbBarChart from '@/components/domain/ProbBarChart'

<DropZone existingCount={items.length} disabled={busy} onAccept={addFiles} />

{successItems.length === 1 && successItems[0]!.result && (
  <Card title="Top-5 候选物种" description="按模型给出的概率从高到低排列，首位为最终判定结果。">
    <ProbBarChart candidates={successItems[0]!.result!.candidates} />
  </Card>
)}
```

`DropZone` 关键设计：统一进入 `handleFiles` → `validateFiles` 客户端校验，不合格不入队；校验失败汇总提示而非逐个弹窗；超 `MAX_BATCH_FILES` 张先询问再静默入队。

```tsx
// frontend/src/components/domain/DropZone.tsx（真实片段）
const handleFiles = useCallback((files: File[], force = false) => {
  if (files.length === 0) return
  const { accepted, rejected, overflow } = validateFiles(files, existingCount, force)
  if (force) {
    if (accepted.length > 0) onAccept(accepted)
    setOverflowCount(0); pendRef.current = []
    return
  }
  setRejects(rejected)
  if (overflow.length > 0) {
    pendRef.current = [...accepted, ...overflow]
    setOverflowCount(overflow.length)
    return
  }
  if (accepted.length > 0) onAccept(accepted)
}, [existingCount, onAccept])
```

`ProbBarChart` 用「首位品牌色 + 其余中性灰」表达层级，置信度保留 1 位小数：

```tsx
// frontend/src/components/domain/ProbBarChart.tsx（真实片段）
const isFirst = highlightIndex !== undefined ? c.class_index === highlightIndex : i === 0
const fill = isFirst ? 'var(--primary)' : 'var(--metric)'
const pct = Math.max(2, (c.confidence / max) * 100)
```

识别作业状态机 `recognizeStore` 用单一 `phase` 字段驱动（idle → ready → uploading → recognizing → done/partial/failed），提交时先并发上传（池=3）再串行识别（防 OOM）：

```ts
// frontend/src/stores/recognizeStore.ts（真实片段）
set({ phase: JOB_PHASE.UPLOADING, doneCount: 0, totalCount: needsRecognize.length })
await runPool(needsRecognize, UPLOAD_CONCURRENCY, async (item) => { /* 上传 */ })
set({ phase: JOB_PHASE.RECOGNIZING })
for (const it of uploaded) {
  const res = await recognizeApi.recognize({ image_id: cur.imageId, top_k: TOP_K })
  if (res.guest_quota) useAuthStore.setState({ guestQuota: res.guest_quota })  // 以服务端为准校准额度
}
```

**验证方法：**
```powershell
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend\src\components\domain\DropZone.tsx"
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend\src\components\domain\ProbBarChart.tsx"
# 预期：两个文件均存在（True）
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend\src\stores\recognizeStore.ts" | Select-String 'JOB_PHASE.RECOGNIZING'
# 预期：命中识别阶段，说明状态机含串行识别
```

**成功标志：**
- DropZone / ProbBarChart / recognizeStore 文件均存在；识别页可渲染上传区、文件队列与 Top-5 概率图；上传与识别分离、识别为串行编排。

### 步骤5：实现历史记录页与后端联调（Axios baseURL + CORS）

**操作内容：**
历史记录 `src/pages/History/List.tsx` 拉取 `/api/records` 并渲染表格/卡片列表，支持筛选与导出。联调核心是 `client.ts`：baseURL 缺省为空（Vite 代理转发），JWT 走 `Authorization: Bearer`，游客走 `X-Guest-Session`。

```ts
// frontend/src/api/client.ts（真实片段：Axios 实例与请求拦截器）
export const client: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '',
  timeout: TIMEOUT_DEFAULT,
  withCredentials: false,
})
client.interceptors.request.use((config) => {
  const h = (config.headers = AxiosHeaders.from(config.headers))
  const token = hooks.getToken()
  if (token) {
    h.set('Authorization', `Bearer ${token}`)
  } else {
    h.set(HEADER_GUEST_SESSION, ensureGuestSessionId()) // 游客计额度
  }
  return config
})
```

后端 CORS 已在 `backend/app/main.py` 放行 5180（`allow_origins` 含 `http://127.0.0.1:5180`，`allow_credentials=True`，`allow_methods/allow_headers=['*']`）。

**验证方法：**
```powershell
# 启动后端（另开终端）：uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend"
npm run dev
Get-NetTCPConnection -LocalPort 5180 -ErrorAction SilentlyContinue | Select-Object -First 1
# 预期：返回一条 5180 监听记录
Invoke-RestMethod -Uri "http://127.0.0.1:5180/api/health" -Method GET | Select-Object -ExpandProperty code
# 预期输出: 0
```

**成功标志：**
- 前端 5180、后端 8000 同时在线；经 5180 代理访问 `/api/health` 返回 `code=0`，联调通道打通、CORS 正常。

### 步骤6：自检 npm run selfcheck（typecheck / lint:tokens / contract:check 118 / route:smoke 12）

**操作命令：**
```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend"
npm run selfcheck
```

**验证方法：**
```powershell
npm run contract:check 2>&1 | Select-String "118"
# 预期：输出出现 118 条契约计数
npm run route:smoke 2>&1 | Select-String "12"
# 预期：输出出现 12 条路由冒烟计数
```

**成功标志：**
- `selfcheck` 四步全部通过，退出码 0；`contract:check` 报告 118 条契约、`route:smoke` 报告 12 条路由均正常。

## 四、验证清单

| 验证项 | 验证方法 | 预期结果 |
|--------|----------|----------|
| 依赖安装 | `npm ls vite antd axios zustand` | 版本与 package.json 一致 |
| 端口配置 | `Select-String 'port: 5180' vite.config.ts` | 命中 5180 且 strictPort: true |
| 代理配置 | `Select-String 'SEATONG_API_TARGET' vite.config.ts` | 命中 /api 代理到 8000 |
| DropZone 存在 | `Test-Path .../DropZone.tsx` | True |
| ProbBarChart 存在 | `Test-Path .../ProbBarChart.tsx` | True |
| 识别页存在 | `Test-Path .../Recognize/index.tsx` | True |
| 历史页存在 | `Test-Path .../History/List.tsx` | True |
| 前端监听 | `Get-NetTCPConnection -LocalPort 5180` | 返回监听记录 |
| 后端联调 | `Invoke-RestMethod http://127.0.0.1:5180/api/health` | 返回 `code=0` |
| 类型检查 | `npm run typecheck` | 退出码 0 |
| 契约核对 | `npm run contract:check` | 报告 118 条契约 |
| 路由冒烟 | `npm run route:smoke` | 报告 12 条路由 |
| 整体自检 | `npm run selfcheck` | 全部通过，退出码 0 |

## 五、故障排除

### 问题1：CORS 报错（浏览器控制台 Access-Control-Allow-Origin 缺失）

**现象：** 前端直连 `http://127.0.0.1:8000/api/...` 时浏览器报跨域。

**解决方案：** 前端请求必须走 Vite 代理（baseURL 缺省为空，不写死 8000）；确认 `vite.config.ts` 的 `/api` 代理与 `main.py` 的 `allow_origins` 含 `http://127.0.0.1:5180`。

```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend\vite.config.ts" | Select-String "'/api'"
# 确认代理段存在；同时确认后端 main.py 含 'http://127.0.0.1:5180'
```

### 问题2：tsc 未找到 / typecheck 失败

**现象：** `npm run typecheck` 报 `tsc: command not found` 或大量类型错误。

**解决方案：** 确认 TypeScript 已作为 devDependency 安装；类型错误多为 `@/` 别名未解析或 `import.meta.env` 类型缺失，检查 `tsconfig.json` 的 `paths` 与 `vite-env.d.ts`。

```powershell
npm ls typescript
# 预期显示 typescript@~5.6.3
```

### 问题3：端口 5180 被占用，dev server 启动失败

**现象：** `npm run dev` 报 `Port 5180 is already in use`（strictPort 下直接退出）。

**解决方案：** 关闭占用 5180 的进程，或临时改 `vite.config.ts` 的 `port`（不推荐）。

```powershell
Get-NetTCPConnection -LocalPort 5180 -ErrorAction SilentlyContinue | Select-Object OwningProcess
```

### 问题4：contract:check 计数不足 118 / route:smoke 不足 12

**现象：** `npm run selfcheck` 在 contract 或 route 阶段失败。

**解决方案：** 检查是否漏建某页面或某接口封装；`contract-check.mjs` 与 `route-smoke.mjs` 是 AI 生成的核对脚本，缺项说明真实端点与契约声明不一致。逐项对照 PRD 的 35 个端点补足 `src/api/*` 与路由声明。

```powershell
Get-ChildItem "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend\src\api" -File | Select-Object Name
# 预期：client / images / recognize / records / types / index 等齐全
```

### 问题5：游客额度不扣减 / 识别后不落库

**现象：** 游客识别成功但额度无变化，或结果未出现在历史记录。

**解决方案：** 这是预期行为——游客结果不落库（`record_id` 为 null），额度在 `/api/recognize` 成功后由后端扣减，前端以响应里的 `guest_quota` 校准。确认请求头带 `X-Guest-Session`（client.ts 已实现）。

```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend\src\api\client.ts" | Select-String 'HEADER_GUEST_SESSION'
# 预期：命中游客会话头设置逻辑
```

## 六、参考代码

### 完整目录结构

```
frontend/
├── index.html / package.json / vite.config.ts / tsconfig.json
├── tailwind.config.js / postcss.config.js / .env.example
├── scripts/{lint-tokens,contract-check,route-smoke}.mjs
└── src/
    ├── api/{client,index,types,images,recognize,records}.ts
    ├── components/base/{Card,Tag}.tsx
    ├── components/domain/{DropZone,ProbBarChart,ResultHero}.tsx
    ├── components/feedback/{Alert,PageSkeleton}.tsx
    ├── constants/{enums,limits,errorMessages}.ts
    ├── hooks/{useReducedMotion,useBreakpoint}.ts
    ├── pages/Recognize/index.tsx / pages/History/List.tsx
    ├── stores/{recognizeStore,authStore,speciesStore,uiStore}.ts
    ├── routes/paths.ts
    └── utils/{format,validate}.ts
```

### 常用命令

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend"
npm install                 # 安装依赖
npm run dev                 # 启动开发服务器（端口 5180）
npm run build               # 生产构建
npm run typecheck           # 类型检查
npm run contract:check      # 契约核对
npm run route:smoke         # 路由冒烟
npm run selfcheck           # 一键自检（串联四项）
npm run preview             # 预览生产包
```

### 关键配置说明

| 参数 / 文件 | 说明 | 示例值 |
|------------|------|--------|
| vite.config.ts / server.port | 前端开发端口（strictPort） | 5180 |
| vite.config.ts / proxy['/api'] | 开发期代理到后端 | http://127.0.0.1:8000 |
| import.meta.env.VITE_API_BASE | Axios baseURL（缺省空，走代理） | '' |
| package.json / selfcheck | 自检串联脚本 | typecheck && lint:tokens && contract:check && route:smoke |
| contract:check | 契约核对条数 | 118 |
| route:smoke | 路由冒烟条数 | 12 |
| HEADER_GUEST_SESSION | 游客会话头（client.ts） | X-Guest-Session |
| Authorization | 登录用户 JWT 头 | Bearer <token> |
