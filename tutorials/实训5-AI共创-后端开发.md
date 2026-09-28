# 实训 5 基于 AI 共创的海瞳鱼鉴后端开发

## 一、实训目标

1. 了解基于 AI 共创的 FastAPI 后端开发协作流程（三文档驱动：PRD / UIUX / 开发任务 + 已生成前端）。
2. 掌握后端工程分层骨架：`api / core / models / schemas / services / utils`。
3. 理解数据库初始化（`scripts/init_db.py`、`seed_data.py`）与 7 张表设计（时间字段 INTEGER Unix 时间戳）。
4. 掌握 JWT 认证与游客免登录试用额度（3 次）的实现与扣减时机。
5. 掌握上传与识别分离、ResNet18 模型推理接入（低置信 <0.60 兜底）与 `uvicorn` 启动验证。

## 二、实训内容

### 1. 背景知识

- **FastAPI**：基于类型提示的高性能 Python Web 框架，自动生成 `/docs` 交互式文档。
- **统一配置口径（务必记牢）**：服务端口 **8000**；API 前缀 **/api**；环境变量前缀 **SEATONG_**；错误码 **40101 未认证 / 40401 他人资源 / 42902 限流（60 次/分）**；时间字段统一 **INTEGER（Unix 时间戳，秒，UTC）**。
- **JWT 认证**：登录用户持 `Authorization: Bearer <token>`；游客靠请求头 `X-Guest-Session` 标识，免登录试用 **3 次**。
- **上传与识别分离**：`POST /api/images` 仅落盘、不推理、不扣额度；`POST /api/recognize` 成功后才扣减游客额度。
- **模型推理**：ResNet18 迁移学习，23 类海洋鱼类细粒度分类；权重 `ml/models/M1_ood_tuned/best.pt`；置信度 <0.60 标记低置信并提示。

### 2. 项目结构

```
backend/
├── app/
│   ├── main.py                       # 入口：CORS / 路由挂载 / /api/health
│   ├── core/{config,database,errors,security,dependencies,middleware}.py
│   ├── models/__init__.py            # 7 表 ORM（时间字段 INTEGER）
│   ├── schemas/                       # Pydantic 请求/响应模型
│   ├── services/{inference,image_service,record_service,user_service}.py
│   ├── api/{auth,users,guest,images,recognize,history,species_admin}.py
│   └── utils/
├── scripts/{init_db,seed_data}.py
├── data/seatong.db                  # SQLite（运行时生成）
├── storage/images/                  # 上传原图
└── requirements.txt
```

## 三、实训步骤

### 步骤1：向 AI 提出后端开发需求（三文档 + 前端驱动）

**操作内容：**
打开与 AI 对话窗口，粘贴以下需求（发送前确认 PRD、UIUX 设计文档、开发任务文档及已生成前端 `frontend/src/api/*` 就位）。

```text
你是一名资深 Python 后端工程师，请基于以下输入完成「海瞳鱼鉴」FastAPI 后端：
1. 产品需求规格说明书（PRD）  2. 界面设计文档（UIUX）
3. 开发任务文档  4. 已生成前端代码（frontend/src/api/*，用于对齐端点契约）

硬性技术约束：
- 框架 FastAPI；ORM SQLAlchemy；数据库 SQLite；深度学习 PyTorch (torchvision ResNet18)
- 端口 8000；所有路由前缀 /api；环境变量前缀 SEATONG_
- 统一响应体 { code, message, data, request_id }，code=0 成功
- 错误码：40101 未认证 / 40401 他人资源 / 42902 限流(60 次/分) / 42901 游客额度耗尽 / 50301 模型未加载
- 时间字段一律 INTEGER（Unix 时间戳，秒，UTC）
- JWT 认证：登录 Bearer；游客 X-Guest-Session，免登录试用 3 次
- 上传与识别分离：POST /api/images 只落盘不推理不扣额度；POST /api/recognize 成功后才扣游客额度
- 模型：resnet18(weights=None)，fc 改为 Sequential(Dropout(p), Linear(512, 23))，
  加载 ml/models/M1_ood_tuned/best.pt；置信度 < 0.60 标记低置信并提示
- 工程分层：app/{api,core,models,schemas,services,utils}
- 提供 scripts/init_db.py 与 scripts/seed_data.py（建 7 张表 + 种子数据）
```

**验证方法：**
```powershell
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\main.py"
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\scripts\init_db.py"
# 预期输出均为 True
```

**成功标志：**
- AI 已产出 `app/` 分层工程与 `scripts/` 初始化脚本；关键文件 `main.py`、`core/config.py`、`core/errors.py`、`api/recognize.py`、`api/images.py` 均存在。

### 步骤2：工程分层骨架与配置层 + 错误码（config.py / errors.py）

**操作内容：**
核对 `core/config.py`：环境变量前缀 `SEATONG_`、端口 8000、API 前缀 `/api`、前端来源 5180、游客额度 3、模型路径、限流 60 次/分。

```python
# backend/app/core/config.py（真实片段）
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='SEATONG_',
        env_file=os.path.join(BACKEND, '.env'),
        env_file_encoding='utf-8',
        extra='ignore',
    )
    app_name: str = '海瞳鱼鉴 SeaPupil'
    api_prefix: str = '/api'
    host: str = '0.0.0.0'
    port: int = 8000
    frontend_origin: str = 'http://localhost:5180'
    guest_quota: int = 3
    model_path: str = os.path.join(ROOT, 'ml', 'models', 'M1_ood_tuned', 'best.pt')
    rate_limit_per_minute: int = 60   # 对应错误码 42902
```

统一响应体与错误码（`core/errors.py`）：PRD §8.3.2 定义 18 个错误码，`ok()` 生成成功体，`BizError` 生成失败体。

```python
# backend/app/core/errors.py（真实片段：关键错误码）
E_40101: Final[int] = 40101  # 未登录或令牌无效
E_40401: Final[int] = 40401  # 资源不存在（含他人资源，防 ID 枚举）
E_42901: Final[int] = 42901  # 游客试用额度已用尽
E_42902: Final[int] = 42902  # 请求过于频繁（限流）
E_50301: Final[int] = 50301  # 识别服务暂不可用（模型未加载）

def ok(data: Any = None, message: str = 'ok') -> dict:
    return {'code': 0, 'message': message, 'data': data}
```

**验证方法：**
```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\core\config.py" | Select-String 'env_prefix='
# 预期：命中 'SEATONG_'
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\core\config.py" | Select-String 'port: int = 8000'
# 预期：命中 port: int = 8000
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\core\errors.py" | Select-String 'E_40101|E_40401|E_42902'
# 预期：命中 40101 / 40401 / 42902 三行定义
python -c "import sys; sys.path.insert(0,'E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend'); import app.core.errors as e; print(len(e.ERROR_TABLE))"
# 预期输出: 18
```

**成功标志：**
- 配置类前缀 `SEATONG_`、端口 8000、`api_prefix=/api`、游客额度 3、限流 60；错误码共 18 项且含 40101/40401/42902。

### 步骤3：数据库初始化（scripts/init_db.py / seed_data.py，7 表）

**操作内容：**
`init_db.py` 调用 `Base.metadata.create_all(engine)` 建表并做体检（7 表 / 64 字段 / 10 显式索引 / 6 外键 / 主键类型）。`seed_data.py` 灌入 23 类物种、5 项 `system_config`、1 个管理员。七张表：`user`、`image_asset`、`recognition_record`、`species`、`system_config`、`operation_log`、`guest_usage`。时间字段统一用 `_ts()` 返回 INTEGER Unix 时间戳。

```python
# backend/app/models/__init__.py（真实片段：时间字段口径）
import time
def _ts() -> int:
    """Unix 时间戳（秒，UTC）。D7 决策 4：时间统一用整数而非文本日期。"""
    return int(time.time())

class User(Base):
    __tablename__ = 'user'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts, onupdate=_ts)
```

**验证方法：**
```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend"
python scripts\init_db.py
# 预期：输出「7 表 / 64 字段 / 10 显式索引 / 6 外键 / 主键类型符合设计」且通过
python scripts\seed_data.py
# 预期：species 新增/更新 23，system_config 5，管理员 1 个；class_index 恰为 0..22
```

**成功标志：**
- `init_db.py` 体检全部通过；`seed_data.py` 回读 `species=23`、`system_config=5`、`user>=1`，`class_index` 取值集合为 0..22。

### 步骤4：JWT 认证与游客额度（dependencies.py，3 次试用）

**操作内容：**
`dependencies.py` 提供 `get_current_user`（必须登录，缺失/无效抛 40101）、`resolve_guest_session`（游客会话头）、`guest_quota_state`（额度状态）、`enforce_guest_quota`（用尽抛 42901）、`consume_guest_quota`（成功后扣减）。游客额度表 `guest_usage` 主键为 `session_id`。

```python
# backend/app/core/dependencies.py（真实片段：游客额度扣减）
def consume_guest_quota(db: Session, guest_session: str | None) -> dict:
    """额度扣减。仅由 /api/recognize 成功返回后调用。"""
    if not guest_session:
        return guest_quota_state(db, None)
    now = int(time.time())
    usage = db.scalar(select(GuestUsage).where(GuestUsage.session_id == guest_session))
    if usage is None:
        usage = GuestUsage(session_id=guest_session, usage_count=1,
                           first_seen_at=now, last_seen_at=now)
        db.add(usage)
    else:
        usage.usage_count += 1
        usage.last_seen_at = now
    db.flush()
    return guest_quota_state(db, guest_session)
```

**验证方法：**
```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\core\dependencies.py" | Select-String 'consume_guest_quota|enforce_guest_quota'
# 预期：命中额度扣减与前置检查两函数
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\core\config.py" | Select-String 'guest_quota: int = 3'
# 预期：命中 guest_quota: int = 3（3 次试用）
```

**成功标志：**
- 额度相关函数存在；配置 `guest_quota = 3`（游客免登录试用 3 次）。

### 步骤5：上传与识别分离 + 限流与错误码（images.py / recognize.py）

**操作内容：**
`POST /api/images` 仅把图片写入磁盘并登记 `image_asset`，【不推理、不扣额度】。`POST /api/recognize` 在推理【成功后】才调用 `consume_guest_quota` 扣减游客额度（登录用户不限额，但结果落库）。限流 `enforce_rate_limit` 为进程内滑动窗口，超过 `rate_limit_per_minute`（60）抛 `E_42902`；归属校验 `assert_can_access` 对他人资源返回 40401（防 ID 枚举）。

```python
# backend/app/api/images.py（真实片段：上传只落盘不扣额度）
@router.post('', dependencies=RATE_LIMIT_DEP)
async def upload_image(db: DbSession, user: OptionalUser, guest: GuestSession,
                       file: UploadFile = File(...)):
    raw = await file.read()
    if not raw:
        raise BizError(E_40001, '上传内容为空')
    user_id = user.id if user is not None else None
    asset, reused = image_service.create_asset(db, raw, file.filename or 'upload.png', user_id)
    db.commit()
    return ok({'image': ImageOut.model_validate(asset).model_dump(), 'reused': reused}, '上传成功')
```

```python
# backend/app/api/recognize.py（真实片段：成功后扣额度 + 限流/归属码）
def _do_recognize(body: RecognizeIn, db, user, guest) -> dict:
    ast = db.get(ImageAsset, body.image_id)
    if ast is None:
        raise BizError(E_40401)
    if user is None:
        enforce_guest_quota(db, guest)          # 额度前置检查（不足 → 42901）
    raw = image_service.read_bytes(ast)
    prediction = engine.predict(raw, top_k=body.top_k)   # 推理
    # ... 登录用户落库；游客不落库 ...
    quota = None
    if user is None:
        quota = consume_guest_quota(db, guest)   # 成功后才扣减
    is_low = prediction['confidence'] < record_service.LOW_CONFIDENCE_THRESHOLD
    return { ... 'is_low_confidence': is_low, 'guest_quota': quota }
```

```python
# backend/app/core/dependencies.py（真实片段：限流 42902）
def enforce_rate_limit(request: Request, client_ip: Annotated[str, Depends(get_client_ip)]) -> None:
    key = client_ip
    now = time.time()
    bucket = _RATE_BUCKETS.setdefault(key, [])
    bucket[:] = [t for t in bucket if now - t < _RATE_WINDOW]
    if len(bucket) >= settings.rate_limit_per_minute:
        raise BizError(E_42902, f'请求过于频繁，每分钟上限 {settings.rate_limit_per_minute} 次')
    bucket.append(now)
```

**验证方法：**
```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\api\images.py" | Select-String 'consume_guest_quota'
# 预期：images.py 不含 consume_guest_quota（上传不扣额度）
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\api\recognize.py" | Select-String 'consume_guest_quota'
# 预期：recognize.py 命中（成功后扣额度）
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\core\dependencies.py" | Select-String 'E_42902'
# 预期：命中 42902 限流分支
```

**成功标志：**
- 上传端点不扣额度，识别端点在成功后扣减；限流抛 42902 且窗口 60 秒；归属校验对他人资源返回 40401。

### 步骤6：模型推理接入（services/inference.py，低置信 <0.60 兜底）

**操作内容：**
推理引擎单例启动时懒加载 ResNet18。结构必须与训练侧一致：`resnet18(weights=None)`，将 `model.fc` 整体替换为 `nn.Sequential(nn.Dropout(p=dropout), nn.Linear(512, 23))`，加载 `ml/models/M1_ood_tuned/best.pt`。置信度低于 `record_service.LOW_CONFIDENCE_THRESHOLD`（0.60）时由 recognize 端点标记 `is_low_confidence=True` 并提示，作为低置信兜底。

```python
# backend/app/services/inference.py（真实片段：模型结构与加载）
model = tvm.resnet18(weights=None)
in_features = model.fc.in_features
model.fc = nn.Sequential(nn.Dropout(p=dropout), nn.Linear(in_features, ncls))
model.load_state_dict(state, strict=True)
model.eval().to(device)

vals, idxs = torch.topk(probs, k)
candidates = [{'rank': r + 1, 'class_index': ci,
               'cn_name': i2cn.get(ci, f'fish_{ci + 1}'),
               'latin_name': i2sci.get(ci, ''),
               'confidence': round(float(p), 6)} for r, (ci, p) in enumerate(zip(idxs, values))]
```

**验证方法：**
```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\services\inference.py" | Select-String 'resnet18\(weights=None\)|nn.Linear\(in_features, ncls\)'
# 预期：命中 ResNet18 结构与 fc 替换
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\core\config.py" | Select-String 'M1_ood_tuned'
# 预期：命中默认模型路径 ml/models/M1_ood_tuned/best.pt
```

**成功标志：**
- 推理代码结构与训练侧一致（fc 为 `Sequential(Dropout, Linear(512,23))`）；默认加载 `best.pt`；存在 0.60 低置信阈值常量。

### 步骤7：uvicorn 启动与验证（/api/health）

**操作命令：**
```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**验证方法：**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -Method GET | Select-Object code, message
# 预期输出: code=0, message=ok
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/model-info" -Method GET | Select-Object code
# 预期: code=0
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -First 1
# 预期：返回一条 8000 监听记录
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/guest/quota" -Method GET -Headers @{ 'X-Guest-Session' = 'selfcheck-session' } | Select-Object code
# 预期输出: code=0（带游客头返回 quota=3）
```

**成功标志：**
- 服务在 8000 启动，`/api/health` 返回 `code=0`；`/api/guest/quota` 带 `X-Guest-Session` 返回 `quota=3`；`/docs` 可打开交互式文档。

## 四、验证清单

| 验证项 | 验证方法 | 预期结果 |
|--------|----------|----------|
| 配置前缀 | `Select-String 'env_prefix=' config.py` | SEATONG_ |
| 服务端口 | `Select-String 'port: int = 8000' config.py` | 8000 |
| API 前缀 | `Select-String "api_prefix: str = '/api'" config.py` | /api |
| 建库体检 | `python scripts\init_db.py` | 7 表 / 64 字段通过 |
| 种子数据 | `python scripts\seed_data.py` | species=23, config=5 |
| 错误码 | `Select-String 'E_40101|E_40401|E_42902' errors.py` | 三码均定义，共 18 |
| 游客额度 | `Select-String 'guest_quota: int = 3' config.py` | 3 次试用 |
| 上传不扣额度 | `Select-String 'consume_guest_quota' images.py` | 无命中 |
| 识别扣额度 | `Select-String 'consume_guest_quota' recognize.py` | 命中（成功后） |
| 模型结构 | `Select-String 'resnet18(weights=None)' inference.py` | 命中 fc Sequential(Dropout,Linear) |
| 限流 | `Select-String 'E_42902' dependencies.py` | 命中 42902 |
| 启动 | `Invoke-RestMethod /api/health` | code=0 |
| 文档 | 浏览器开 `http://127.0.0.1:8000/docs` | 可见 35 个端点 |

## 五、故障排除

### 问题1：模型加载失败，/api/health 显示 ready=False（503 风险）

**现象：** 启动后控制台打印「模型未就绪」，或推理时返回 50301。

**解决方案：** 检查 `SEATONG_MODEL_PATH` 指向的 `best.pt` 是否存在；确认 PyTorch / torchvision 已安装且版本兼容。

```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\core\config.py" | Select-String 'model_path'
Test-Path "E:\基于CNN的海洋鱼类图像分类系统\ml\models\M1_ood_tuned\best.pt"
# 预期: True（路径以实际 ROOT 为准）
```

### 问题2：42902 限流被频繁触发

**现象：** 连续请求时出现「请求过于频繁，每分钟上限 60 次」。

**解决方案：** 进程内滑动窗口限流（对应 42902），单机每 IP 每 60 秒 60 次。自检/压测时放慢频率，或临时调大 `SEATONG_RATE_LIMIT_PER_MINUTE`。生产多实例需换 Redis。

```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\core\config.py" | Select-String 'rate_limit_per_minute'
# 确认阈值 60
```

### 问题3：端口 8000 被占用，uvicorn 启动失败

**现象：** `uvicorn` 报 `Address already in use`。

**解决方案：** 查占用 8000 的进程并结束，或改用其他端口（需同步修改前端代理目标与 `frontend_origin`）。

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object OwningProcess
```

### 问题4：游客额度不扣减 / 40101 未认证

**现象：** 游客识别不消耗额度，或带游客头仍返回 40101。

**解决方案：** 确认请求头携带 `X-Guest-Session`；额度仅在 `/api/recognize` 成功返回后由 `consume_guest_quota` 扣减。若一直 40101，检查 `get_optional_user` 是否允许游客（无 token 时返回 None 而非抛错）。

```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\api\recognize.py" | Select-String 'enforce_guest_quota'
# 预期：识别前做额度前置检查，命中 42901 分支逻辑
```

### 问题5：时间字段存成文本日期而非 INTEGER

**现象：** 报表或排序异常，`created_at` 显示为字符串。

**解决方案：** 所有时间字段必须声明为 `Integer` 且 `default=_ts`（Unix 时间戳）。核查 `models/__init__.py` 中 `created_at/updated_at/locked_until/expires_at` 是否均为 `Integer`；若已落库为文本，需重建数据库后重新 `init_db.py` + `seed_data.py`。

```powershell
Get-Content "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend\app\models\__init__.py" | Select-String 'created_at: Mapped\[int\]'
# 预期：命中多行 Integer 时间字段声明
```

## 六、参考代码

### 完整目录结构

```
backend/
├── app/
│   ├── main.py
│   ├── core/{config,database,errors,security,dependencies,middleware}.py
│   ├── models/__init__.py                 # 7 表：user/image_asset/recognition_record/
│   │                                      #     species/system_config/operation_log/guest_usage
│   ├── schemas/                           # Pydantic 模型
│   ├── services/{inference,image_service,record_service,user_service}.py
│   ├── api/{auth,users,guest,images,recognize,history,species_admin}.py
│   └── utils/
├── scripts/{init_db,seed_data}.py
├── data/seatong.db
├── storage/images/
└── requirements.txt
```

### 常用命令

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\backend"
pip install -r requirements.txt      # 安装依赖
python app\core\config.py            # 配置自检（端口/路径/额度）
python scripts\init_db.py            # 建库 + 体检
python scripts\seed_data.py          # 种子数据
python app\core\dependencies.py      # 依赖层离线自检
python app\core\errors.py            # 错误码清单自检
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload   # 启动（端口 8000）
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -Method GET   # 健康检查
```

### 关键配置说明

| 参数 / 环境变量 | 说明 | 示例值 |
|------------|------|--------|
| SEATONG_PORT | 服务端口 | 8000 |
| SEATONG_API_PREFIX | API 前缀 | /api |
| SEATONG_（前缀） | 所有配置项环境变量前缀 | SEATONG_ |
| SEATONG_MODEL_PATH | 模型权重路径 | ml/models/M1_ood_tuned/best.pt |
| SEATONG_GUEST_QUOTA | 游客试用次数 | 3 |
| SEATONG_RATE_LIMIT_PER_MINUTE | 限流阈值（42902） | 60 |
| 时间字段 | INTEGER Unix 时间戳（秒，UTC） | created_at/updated_at 等 |
| 错误码 40101 | 未认证 | 令牌缺失/无效 |
| 错误码 40401 | 他人资源（防枚举） | 返回 404 而非 403 |
| 错误码 42902 | 限流 | 每分钟 60 次 |
| LOW_CONFIDENCE_THRESHOLD | 低置信兜底阈值 | 0.60 |
