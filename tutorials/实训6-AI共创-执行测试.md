# 实训 6 基于 AI 共创的海瞳鱼鉴测试

## 一、实训目标

1. 理解软件测试在图像分类系统交付中的价值，掌握单元测试、集成测试、契约测试、验收测试的分层方法
2. 学会借助 AI 共创生成并运行海瞳鱼鉴（Seatong）后端 pytest 测试套件，验证 348 项断言全绿
3. 掌握前端 `npm run selfcheck` 自检测量与浏览器端 E2E 流程验证的方法
4. 理解性能验收的量化口径，能够对标 PRD 第 9 章"端到端 ≤ 3000 ms"预算
5. 能够独立排查限流、探针节流、数据库连接隔离等测试期常见故障

## 二、实训内容

### 1. 背景知识

- **软件测试分层**：海瞳鱼鉴采用六类测试协同保证质量。逻辑与契约由 `TestClient + 临时库` 在进程内实跑；运行态由探针（probe）对真实服务做 HTTP 冒烟与全链路验收。
- **测试隔离**：所有 `TestClient` 套件均改写 `SEATONG_DB_PATH`、`SEATONG_IMAGE_STORAGE_DIR`、`SEATONG_LOG_DIR` 三个环境变量，跑在独立的临时库与临时存储目录上，绝不触碰 `backend/data/seatong.db` 与 `backend/storage/images`。
- **契约一致性**：后端响应统一使用信封结构（`code / message / data / request_id`），`X-Skip-Envelope` 可跳过信封；测试覆盖信封结构、错误码与三方（文档 / 配置 / 实际运行）对账。
- **限流与节流**：后端内置 60 次/分钟的限流（错误码 42902）；验收探针 `probe_acceptance.py` 对每一次请求强制 1.15 s 间隔节流，使长期速率稳定在约 52 次/分钟，从源头规避限流而非失败后退避。
- **性能预算**：PRD 第 9 章规定端到端响应 ≤ 3000 ms，需拆解上传 / 预处理 / 推理 / 落库 / 渲染五段分别实测。

### 2. 项目结构与测试分布

```
E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\
├── backend\
│   ├── app\
│   │   ├── core\config.py          # get_settings()
│   │   ├── main.py                 # FastAPI 入口
│   │   └── ...
│   ├── tests\
│   │   ├── test_e2e.py             # 端到端集成（119 项断言）
│   │   ├── test_nfr_audit.py       # D7 结构 / NFR 审计（79 项）
│   │   ├── test_contract_triptych.py # 契约三方对账（17 项）
│   │   ├── probe_new_endpoints.py  # 新增端点专项（50 项）
│   │   ├── probe_live_server.py    # live HTTP 冒烟（39 项）
│   │   └── probe_acceptance.py     # 验收级全链路 + 性能分段（83 项）
│   └── data\seatong.db             # 生产库（测试不触碰）
└── frontend\
    ├── package.json                # 含 selfcheck 脚本
    └── scripts\e2e-flow.mjs        # 浏览器 E2E（22 项）
```

### 3. 后端测试套件总览（总计 348 项断言全绿）

| 测试文件 | 类别 | 断言数 | 运行方式 |
|----------|------|--------|----------|
| test_e2e.py | 端到端集成（认证 / 游客 / 全链路 / 错误码 / 权限） | 119 | pytest |
| test_nfr_audit.py | D7 结构 / NFR 审计 | 79 | pytest |
| test_contract_triptych.py | 契约三方对账 | 17 | pytest |
| probe_new_endpoints.py | 新增端点专项 | 50 | 真实服务 |
| probe_live_server.py | live HTTP 冒烟 | 39 | 真实服务 |
| probe_acceptance.py | 验收级全链路 + PRD §9 性能分段 | 83 | 真实服务 |
| **合计** | | **348** | 全绿 |

## 三、实训步骤

### 步骤 1：与 AI 共创生成测试任务

**操作命令：**

打开与 AI 的对话窗口，输入以下指令，让 AI 基于整个海瞳鱼鉴项目生成测试任务并执行：

```text
请根据整个海瞳鱼鉴（Seatong）海洋鱼类图像分类系统，生成一份测试任务，
并对后端生成单元测试、集成测试、契约测试，对前端生成自检测量与浏览器 E2E 流程测试。
要求覆盖：认证链路、游客额度、上传→识别→历史→导出→删除全链路、错误码、权限、
NFR 审计、契约三方对账、性能分段验收。
```

**验证方法：**

```powershell
# 确认 AI 已生成后端测试套件
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\tests\test_e2e.py"
# 预期输出: True

# 确认前端 E2E 脚本存在
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend\scripts\e2e-flow.mjs"
# 预期输出: True
```

**成功标志：**
- AI 先创建任务列表跟踪工作，再逐一实现测试文件
- 测试目录中出现 `test_e2e.py` 等 6 个测试文件
- 前端目录下出现 `e2e-flow.mjs`

### 步骤 2：启动后端服务（供探针类测试连接）

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend"
$env:SEATONG_DEBUG = "false"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**验证方法：**

```powershell
# 健康检查
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -Method GET
# 预期输出: 返回 JSON，形如 {"status":"ok"} 或带 code/data 的信封
```

**成功标志：**
- 终端显示 `Uvicorn running on http://127.0.0.1:8000`
- `/api/health` 返回 200 与合法 JSON

### 步骤 3：运行后端 pytest 套件（隔离、119+79+17 = 215 项）

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend"
python -m pytest tests/test_e2e.py tests/test_nfr_audit.py tests/test_contract_triptych.py -v
```

**验证方法：**

```powershell
# 仅运行断言数最多的端到端套件并查看计数
python -m pytest tests/test_e2e.py -v 2>&1 | Select-String -Pattern "passed|failed"
# 预期输出: 含 "119 passed" 之类计数，无 failed
```

**成功标志：**
- `test_e2e.py` 报告 119 项断言通过
- `test_nfr_audit.py` 报告 79 项通过
- `test_contract_triptych.py` 报告 17 项通过
- 临时库位于 `tempfile.mkdtemp(prefix='seatong_test_')`，生产库 `seatong.db` 未被修改

### 步骤 4：运行 live 探针（真实服务，39 + 50 = 89 项）

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend"
python tests/probe_live_server.py
python tests/probe_new_endpoints.py
```

**验证方法：**

```powershell
# 检查退出码（0 表示全通过）
python tests/probe_live_server.py; Write-Host "EXIT=$LASTEXITCODE"
# 预期输出: EXIT=0
```

**成功标志：**
- `probe_live_server.py` 报告 39 项 HTTP 冒烟全绿
- `probe_new_endpoints.py` 报告 50 项新增端点专项全绿

### 步骤 5：运行验收探针（83 项 + 性能分段）

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend"
# 默认对 127.0.0.1:8000 与前端 127.0.0.1:5180 做全链路验收
python tests/probe_acceptance.py
# 可选：指定样本数、跳过阶段微基准、保留账号
python tests/probe_acceptance.py --samples 12 --skip-stage-bench --no-cleanup
```

> 注意：探针内置 `MIN_GAP_S = 1.15` 的节流，每一次请求间隔至少 1.15 s，长期速率约 52 次/分钟，低于后端 60 次/分钟上限，避免触发 42902 限流。请勿在循环中手动高频调用接口。

**验证方法：**

```powershell
python tests/probe_acceptance.py; Write-Host "EXIT=$LASTEXITCODE"
# 预期输出: EXIT=0，并打印拓扑一致性、游客链路、注册用户全链路、性能分段结果
```

**成功标志：**
- 拓扑一致性：文档声明 / 配置 / 实际运行 的端口与跨域口径一致
- 游客链路：额度 3 → 0 → 42901 逐环节断言通过
- 注册用户链路：上传 → 识别 → 落库 → 历史 → 候选 → 导出 → 删除 全绿
- 善后：本轮创建的账号与图像被清理（teardown）
- 退出码为 0，合计 83 项通过

### 步骤 6：前端自检测量（npm run selfcheck，四项）

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend"
npm install
npm run selfcheck
```

**验证方法：**

```powershell
# 查看 selfcheck 输出，确认四项自检通过
npm run selfcheck 2>&1 | Select-String -Pattern "PASS|FAIL|OK|error"
# 预期输出: 四项均显示 PASS / OK，无 FAIL / error
```

**成功标志：**
- 前端自检四项（依赖完整性、构建配置、类型/语法、脚本可用性）全部通过
- 终端无 error 级输出

### 步骤 7：浏览器端 E2E 流程（e2e-flow.mjs，22 项）

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend"
# 先确保后端 8000 与前端 dev server 5180 已运行
npm run dev
# 另开终端执行浏览器 E2E
node scripts/e2e-flow.mjs
```

**验证方法：**

```powershell
node scripts/e2e-flow.mjs 2>&1 | Select-String -Pattern "passed|failed|✓|✗"
# 预期输出: 含 "22 passed" 计数，无 ✗ / failed
```

**成功标志：**
- 三条旅程共 22 项断言全绿：
  - 游客识别旅程（无需登录即可识别、额度可见）
  - 额度本地拦截（本地在前端拦截超出 3 次的请求，不打到后端）
  - 登录 + 历史旅程（登录后上传识别、写入历史、可查历史与导出）
- 退出码为 0

### 步骤 8：性能验收（端到端 p50 对标 3000 ms 预算）

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend"
python tests/probe_acceptance.py --samples 12
```

**验证方法：**

```powershell
# 在探针输出中查找端到端分段与 p50 数值
python tests/probe_acceptance.py 2>&1 | Select-String -Pattern "p50|3000|上传|预处理|推理|落库|渲染"
# 预期输出: 端到端 p50 ≈ 90.8 ms，远低于预算 3000 ms
```

**成功标志：**
- 端到端 p50 = 90.8 ms，对比 PRD §9 预算 3000 ms，余量充足
- 五段（上传 / 预处理 / 推理 / 落库 / 渲染）实测值均在预算占比内

## 四、验证清单

完成所有步骤后，请确认以下验证项：

| 验证项 | 验证方法 | 预期结果 |
|--------|----------|----------|
| 后端服务 | `Invoke-RestMethod /api/health` | 返回 200 与合法 JSON |
| test_e2e | `pytest tests/test_e2e.py` | 119 项 passed |
| test_nfr_audit | `pytest tests/test_nfr_audit.py` | 79 项 passed |
| test_contract | `pytest tests/test_contract_triptych.py` | 17 项 passed |
| probe_live | `python tests/probe_live_server.py` | 39 项，EXIT=0 |
| probe_new | `python tests/probe_new_endpoints.py` | 50 项，EXIT=0 |
| probe_acceptance | `python tests/probe_acceptance.py` | 83 项，EXIT=0 |
| 测试隔离 | 检查 `backend/data/seatong.db` 修改时间 | 运行前后未变动 |
| 前端自检 | `npm run selfcheck` | 四项 PASS |
| 浏览器 E2E | `node scripts/e2e-flow.mjs` | 22 项 passed |
| 性能预算 | 探针性能分段输出 | 端到端 p50 ≈ 90.8 ms ≤ 3000 ms |
| 限流规避 | 探针日志无 42902 | 探针未触发限流 |
| 总计 | 六文件合计 | 348 项全绿 |

## 五、故障排除

### 问题 1：pytest 提示找不到 `app` 模块或 `SEATONG_DB_PATH` 未生效

**现象：** 运行 `pytest` 报 `ModuleNotFoundError: No module named 'app'`，或测试改写的临时库未隔离、直接写到了生产库。

**解决方案：**

```powershell
# 必须在 backend 目录内执行，确保 app 在 sys.path
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend"
# 确认 test_e2e.py 在导入 app 之前已改写环境变量并 clear lru_cache
Select-String -Path "tests/test_e2e.py" -Pattern "SEATONG_DB_PATH|get_settings.cache_clear"
# 预期输出: 命中对应行；若缺失说明文件被改动，需恢复隔离代码
```

### 问题 2：探针返回退出码 2（服务不可达）或 1（有失败项）

**现象：** `probe_acceptance.py` 报 `EXIT=2`，或某链路断言失败。

**解决方案：**

```powershell
# 确认后端已启动且监听 8000
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
# 预期输出: 显示 LISTENING 状态

# 确认前端 dev server 已启动（验收探针默认连 5180）
Get-NetTCPConnection -LocalPort 5180 -ErrorAction SilentlyContinue

# 若服务在，但探针仍失败，多为限流；确保未手动高频调用
# 探针内置 MIN_GAP_S=1.15 节流，切勿在外层循环再加速
```

### 问题 3：浏览器 E2E 报额度本地拦截不生效

**现象：** 游客第 4 次识别仍打到后端，未在本地拦截；或 e2e-flow.mjs 报错。

**解决方案：**

```powershell
# 确认前端 dev server 与后端均已运行（E2E 依赖两者）
# 确认 e2e-flow.mjs 读取的地址与本地一致
Select-String -Path "scripts/e2e-flow.mjs" -Pattern "127.0.0.1:8000|127.0.0.1:5180"
# 若地址不符，通过环境变量 SEATONG_BASE / SEATONG_FRONTEND 覆盖
$env:SEATONG_BASE = "http://127.0.0.1:8000"
$env:SEATONG_FRONTEND = "http://127.0.0.1:5180"
node scripts/e2e-flow.mjs
```

### 问题 4：性能分段显示端到端远超 3000 ms

**现象：** 探针输出的端到端 p50 明显大于预算，或某段耗时异常。

**解决方案：**

```powershell
# 确认未开启调试日志（调试日志会拖慢落库/渲染段）
$env:SEATONG_DEBUG = "false"
# 确认本机 GPU 可用；CPU 推理会显著拉长"推理"段
python -c "import torch; print(torch.cuda.is_available())"
# 预期输出: True；若为 False，检查 CUDA 12.6 与 torch cu126 安装
```

### 问题 5：npm run selfcheck 报依赖缺失

**现象：** 前端自检失败，提示某包未安装或脚本不存在。

**解决方案：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend"
npm install
npm run selfcheck
```

## 六、参考代码

### 完整目录结构

```
E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\
├── backend\
│   ├── app\
│   │   ├── core\config.py
│   │   └── main.py
│   ├── tests\
│   │   ├── test_e2e.py
│   │   ├── test_nfr_audit.py
│   │   ├── test_contract_triptych.py
│   │   ├── probe_new_endpoints.py
│   │   ├── probe_live_server.py
│   │   └── probe_acceptance.py
│   ├── data\seatong.db
│   └── storage\images\
└── frontend\
    ├── package.json
    └── scripts\e2e-flow.mjs
```

### 常用命令

```powershell
# 启动后端
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 进程内 pytest 套件（隔离库，215 项）
python -m pytest tests/test_e2e.py tests/test_nfr_audit.py tests/test_contract_triptych.py -v

# 真实服务探针（139 项）
python tests/probe_live_server.py
python tests/probe_new_endpoints.py
python tests/probe_acceptance.py

# 前端
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\frontend"
npm install
npm run selfcheck
npm run dev
node scripts/e2e-flow.mjs
```

### 探针节流与限流关键配置说明

| 参数 | 位置 | 说明 | 示例 |
|------|------|------|------|
| `SEATONG_DB_PATH` | test_e2e.py 头部 | 测试隔离临时库路径 | `tempfile.mkdtemp(prefix='seatong_test_')/test.db` |
| 后端限流 | 后端中间件 | 60 次/分钟触发 42902 | 错误码 42902 |
| `MIN_GAP_S` | probe_acceptance.py | 探针每次请求间隔（节流） | 1.15 秒 |
| 探针有效速率 | probe_acceptance.py | 1.15 s 间隔 → 约 52 次/分钟 | 低于 60 上限 |
| `SEATONG_BASE` | 探针环境变量 | 后端基址覆盖 | `http://127.0.0.1:8000` |
| `SEATONG_FRONTEND` | 探针环境变量 | 前端基址覆盖 | `http://127.0.0.1:5180` |

### 后端测试套件断言分布表

| 测试文件 | 断言数 | 对应实训目标 |
|----------|--------|--------------|
| test_e2e.py | 119 | 认证 / 游客 / 全链路 / 错误码 / 权限 / 信封契约 |
| test_nfr_audit.py | 79 | D7 结构审计、NFR 合规 |
| test_contract_triptych.py | 17 | 文档 / 配置 / 运行 三方对账 |
| probe_new_endpoints.py | 50 | 新增端点专项 |
| probe_live_server.py | 39 | live HTTP 冒烟 |
| probe_acceptance.py | 83 | 验收全链路 + 性能分段 |
| 合计 | 348 | 全绿 |
