# API接口使用语料库

**主题：** 38端点分组说明、关键端点请求/响应示例、错误码对照、调用示例（PowerShell Invoke-RestMethod / curl）  
**适用范围：** 前后端对接、接口联调、二次开发、实训学员  
**版本：** v1.0

---

## Q: 海瞳鱼鉴后端共有多少端点？如何分组？

**A:** 后端共 38 个端点，API 前缀为 `/api`。按路由模块分组：auth（认证）、images（图像）、recognize（识别）、history/records（历史）、users（用户）、guest（游客）、species_admin（物种后台）等，由 `app/api/` 各路由承载。

**标签：** 端点总数, 38端点, api前缀, 路由分组, app_api

---

## Q: 后端 API 前缀与端口是什么？

**A:** 所有接口以 `/api` 为前缀，后端 uvicorn 监听 8000 端口（开发可 0.0.0.0，生产仅 127.0.0.1 由 Nginx 反代）。健康检查示例 `GET /api/health`。

**标签：** API前缀, 端口8000, 127_0_0_1, Nginx反代, health

---

## Q: POST /api/images 的请求与响应？

**A:** 请求为 multipart 上传图像（单图 ≤10MB、批量 ≤9 张、PNG/JPEG），仅落盘返回图像 ID，不扣游客额度。响应 `code=0` 带图像标识，供后续识别引用。

**标签：** POST_images, 上传落盘, 不扣额度, multipart, 图像ID

---

## Q: POST /api/recognize 的请求与响应？

**A:** 请求携带图像 ID（可由 `/api/images` 获得），执行推理。响应 `code=0` 返回 Top-1 物种、置信度、Top-5 候选与物种介绍，并扣减游客额度、写入历史。

**标签：** POST_recognize, 图像ID, Top-5, 扣额度, 写历史

---

## Q: GET /api/records 的作用与示例？

**A:** 查询当前用户历史识别记录，支持时间/物种/置信度筛选。需登录（JWT）。示例：`Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/records" -Headers @{Authorization="Bearer $token"}`。

**标签：** GET_records, 历史查询, 筛选, JWT, 登录

---

## Q: GET /api/guest/quota 的作用？

**A:** 返回游客剩余试用额度（初始 3 次）。匿名可访问，用于前端展示游客还可识别几次；用尽后引导注册登录。

**标签：** GET_guest_quota, 游客额度, 剩余次数, 匿名访问, 引导

---

## Q: GET /api/users/me 的作用？

**A:** 返回当前登录用户自身信息（用户名、角色等）。需携带 JWT，令牌无效返回 40101，过期返回 40102。

**标签：** GET_users_me, 当前用户, JWT, 40101, 40102

---

## Q: DELETE /api/images 的约束？

**A:** 删除图像；对已识别图像返回 42201（防级联丢失历史），仅未识别暂存图可删。示例需携带图像 ID 与 JWT（若属用户资源）。

**标签：** DELETE_images, 已识别不可删, 42201, 暂存可删, JWT

---

## Q: DELETE /api/records 的作用？

**A:** 删除指定历史记录。需登录且只能删本人记录，查询他人返回 40401（资源不存在）。删除后关联图像按规则处理。

**标签：** DELETE_records, 删除历史, 本人记录, 40401, 关联处理

---

## Q: 认证类端点有哪些？

**A:** auth 模块含注册、登录、刷新/校验令牌等。登录失败 40103、禁用 40104、锁定 40105；成功签发 JWT 短期令牌供后续端点使用。

**标签：** 认证端点, auth模块, 登录, 40103, JWT

---

## Q: 游客端点（guest）有哪些？

**A:** guest 模块含 `GET /api/guest/quota` 等，支持匿名查询剩余额度；上传与识别端点亦允许匿名但受 3 次额度约束，用尽返回 42901。

**标签：** 游客端点, guest模块, 匿名, 3次, 42901

---

## Q: 用户管理端点（users）有哪些？

**A:** users 模块含 `GET /api/users/me`、用户列表/详情（管理员）等。普通用户查他人资源返回 40401；管理员可管理用户（禁用/锁定）。

**标签：** 用户端点, users模块, users_me, 40401, 管理员

---

## Q: 物种后台端点（species_admin）有哪些？

**A:** species_admin 维护 23 类元数据与介绍（fish_1~fish_23 / species_id 0~22）。仅管理员可访问，角色不足返回 40301。

**标签：** 物种后台, species_admin, 23类, 管理员, 40301

---

## Q: 调用示例（PowerShell Invoke-RestMethod）？

**A:** 健康检查：`Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"`；带令牌：`Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/users/me" -Headers @{Authorization="Bearer $token"}`。

**标签：** PowerShell, Invoke-RestMethod, 健康检查, Bearer, 调用示例

---

## Q: 调用示例（curl）？

**A:** 健康检查：`curl http://127.0.0.1:8000/api/health`；带令牌：`curl -H "Authorization: Bearer $token" http://127.0.0.1:8000/api/users/me`。生产经 HTTPS 域名访问。

**标签：** curl, 健康检查, Bearer, HTTPS, 调用示例

---

## Q: 统一响应体结构如何解析？

**A:** 响应为 `{ "code": 0, "message": "ok", "data": {...}, "request_id": "..." }`。前端判断 `code==0` 取 `data`；非 0 时按 `code` 查错误码表展示文案，`request_id` 用于排障。

**标签：** 响应体, code_0, data, request_id, 错误码

---

## Q: 错误码与 HTTP 状态对照总表？

**A:** 分段：40001(400) 参数、40101/02/03/04/05(401) 认证账号、40301(403) 权限、40401(404) 资源、40901(409) 冲突、41301(413) 体积、41501(415) 类型、42201/02(422) 语义、42901/02(429) 限流、50001(500) 内部、50301/02(503) 不可用。

**标签：** 错误码表, HTTP状态, 40001, 50302, 对照

---

## Q: 上传接口的限流与体积限制如何叠加？

**A:** 单图 ≤10MB、批量 ≤9 张由业务校验（41301/41501）；频率由后端 60 次/分钟限流（42902），Nginx `client_max_body_size 100m` 再拦截超大请求。三层防护。

**标签：** 上传限制, 10MB, 9张, 42902, client_max_body_size

---

## Q: 识别接口如何避免重复扣额度？

**A:** 额度在识别成功（推理完成且写入历史）后扣减；上传不扣。失败或异常不扣额度，保证游客 3 次仅统计有效识别。

**标签：** 扣额度, 识别成功, 上传不扣, 失败不扣, 3次统计

---

## Q: 前端如何封装这些接口？

**A:** 前端在 `src/api/` 用 Axios 定义各端点封装，统一附加 JWT 与错误码处理；`npm run selfcheck` 的 `contract:check` 对账 118 项接口契约确保前后端一致。

**标签：** 前端封装, src_api, Axios, 错误码处理, contract_check

---

## Q: 接口契约如何校验？

**A:** 通过 `tools/api_contract_verify.py` 与前端 `contract:check`（118 项）对账请求/响应结构；不一致会导致 selfcheck 失败，需修正前后端定义。

**标签：** 接口契约, api_contract_verify, contract_check, 118项, 对账

---

## Q: 端到端接口链路示例？

**A:** 游客：`GET /api/guest/quota` → `POST /api/images`（落盘）→ `POST /api/recognize`（扣额、返回结果）→ `GET /api/records`（登录后查历史）。匿名仅前两步与识别受限。

**标签：** 接口链路, guest_quota, images, recognize, records

---

## Q: 为何识别与上传分开调用而非一次完成？

**A:** 分离让上传只落盘（失败不计费），识别才消耗算力并扣额度，前端可先批量上传再逐张识别，灵活且利于额度精确结算与历史关联。

**标签：** 分离调用, 上传落盘, 识别扣额, 批量上传, 灵活

---

## Q: 历史记录分页与筛选参数？

**A:** `GET /api/records` 支持按时间范围、species_id（0~22）、置信度区间筛选，并分页返回。具体分页参数以接口契约（contract:check 118 项）为准。

**标签：** 历史分页, 筛选参数, species_id, 置信度, 接口契约

---

## Q: 调用频率过高如何规避 42902？

**A:** 后端限流 60 次/分钟，调用方自行节流（如间隔 ≥1.15s）；Nginx 亦可叠加 `limit_req`（rate=30r/m、burst=20）。触发 42902 稍后重试即可。

**标签：** 规避限流, 60次每分, 1_15s间隔, limit_req, 42902

---

## Q: 模型相关端点或配置如何访问？

**A:** 模型不暴露独立写端点，通过环境变量 `SEATONG_MODEL_PATH` 指定加载路径（默认 `M1_ood_tuned/best.pt`，回滚 `M1_main_224/best.pt`），属部署/配置层面而非运行时 API。

**标签：** 模型配置, SEATONG_MODEL_PATH, M1_ood_tuned, M1_main_224, 非API

---

## Q: 错误响应中 detail 字段用途？

**A:** `fail(code, message, detail)` 中 `detail` 携带附加诊断信息（如字段名、体积值），前端可按需展示；`request_id` 配合 `detail` 便于后端日志定位。

**标签：** detail字段, 诊断信息, fail, request_id, 日志定位

---

## Q: 刷新令牌或重新登录的接口？

**A:** 令牌过期返回 40102，客户端应引导用户重新登录以获取新 JWT；当前实现为短期令牌模式，无独立 refresh 端点描述，以重新登录为准。

**标签：** 刷新令牌, 40102, 重新登录, 短期令牌, JWT

---

## Q: 接入第三方系统应注意什么？

**A:** 第三方须走 `/api` 前缀、携带 JWT（受保护端点）、遵守 60 次/分钟限流与单图 10MB/批量 9 张限制；错误按 28 条业务码处理，勿依赖 HTTP 状态 alone。

**标签：** 第三方接入, api前缀, JWT, 限流, 28条错误码

---

## Q: 接口总数 38 与契约 118 项的关系？

**A:** 38 为端点数量；118 为前端 `contract:check` 对账的接口契约条目数（含各端点的请求/响应字段、错误码等细项），两者口径不同，分别衡量端点覆盖与字段一致性。

**标签：** 38端点, 118契约, 端点数量, 字段对账, 口径不同
