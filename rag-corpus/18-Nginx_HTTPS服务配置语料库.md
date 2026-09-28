# Nginx_HTTPS服务配置语料库

**主题：** Nginx安装、SSL自签证书生成、server块配置（443 ssl、前端静态托管、try_files回退、/api反代、client_max_body_size、limit_req）、80跳转443、upstream多实例负载均衡、配置校验与重载  
**适用范围：** 运维、部署工程师、网络配置人员  
**版本：** v1.0

---

## Q: 海瞳鱼鉴生产为何用 Nginx？

**A:** Nginx 作为对外入口，托管前端静态资源（`frontend-dist/`）并将 `/api` 反向代理至后端 uvicorn（127.0.0.1:8000），同时提供 HTTPS、限流与负载均衡能力。

**标签：** Nginx, 反向代理, HTTPS, 前端托管, 反代

---

## Q: Nginx 版本与运行环境要求？

**A:** 生产要求 Nginx 1.24+，运行于 Windows Server/10/11 或 Linux；需 OpenSSL 生成自签证书。Windows 下可执行文件为 `nginx.exe`，命令同 Linux。

**标签：** Nginx版本, 1_24, OpenSSL, Windows, nginx_exe

---

## Q: 如何生成自签 SSL 证书？

**A:** 执行 `openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout seatong.key -out seatong.crt -subj "/CN=seatong.local"`，生成私钥与证书，供 `ssl_certificate`/`ssl_certificate_key` 引用。

**标签：** 自签证书, openssl, req_x509, seatong_crt, rsa_2048

---

## Q: 自签证书的适用场景？

**A:** 自签证书仅适用于内网/教学环境；生产环境应使用受信任 CA 签发的证书，避免浏览器告警。自签证书有效期由 `-days` 控制（示例 365 天）。

**标签：** 自签场景, 内网教学, 受信任CA, 证书有效期, 浏览器告警

---

## Q: HTTPS server 块核心配置？

**A:** `listen 443 ssl;` + `server_name` + `ssl_certificate`/`ssl_certificate_key` 指向证书，`ssl_protocols TLSv1.2 TLSv1.3`，`ssl_ciphers HIGH:!aNULL:!MD5`。这是 443 ssl 主站基础。

**标签：** HTTPS_server, 443_ssl, ssl_certificate, TLSv1_2, ssl_ciphers

---

## Q: 前端静态资源如何托管？

**A:** `location /` 设 `root html/seatong;`（frontend-dist 内容），`index index.html;`，并配 `try_files $uri $uri/ /index.html;` 实现 SPA 路由回退，刷新二级路由不 404。

**标签：** 前端托管, location, root, index_html, SPA回退

---

## Q: 为何需要 try_files 回退？

**A:** 前端为 SPA，路由由 JS 控制，直接访问二级路径时 Nginx 找不到物理文件会 404。`try_files ... /index.html` 将未知路径回退到首页，由前端路由接管，避免刷新 404。

**标签：** try_files, SPA, 二级路由, 404避免, 路由接管

---

## Q: /api 反代如何配置？

**A:** `location /api/ { proxy_pass http://127.0.0.1:8000; proxy_set_header Host/X-Real-IP/X-Forwarded-For/X-Forwarded-Proto; }`。注意 `proxy_pass` 末尾斜杠与 `/api/` 匹配。

**标签：** api反代, location_api, proxy_pass, 8000, proxy_set_header

---

## Q: client_max_body_size 如何设置？

**A:** 在 `http` 或 `server` 块设 `client_max_body_size 100m;`。单图 ≤10MB、批量 ≤9 张，100m 预留余量避免上传触发 413；修改后 `nginx -s reload`。

**标签：** client_max_body_size, 100m, 上传体积, 413避免, reload

---

## Q: Nginx 侧如何叠加限流？

**A:** 定义 `limit_req_zone $binary_remote_addr zone=seatong_api:10m rate=30r/m;`，在 `location /api/` 用 `limit_req zone=seatong_api burst=20 nodelay;`。与后端 60 次/分钟形成双层防护。

**标签：** Nginx限流, limit_req_zone, rate_30r_m, burst_20, 双层防护

---

## Q: HTTP 80 如何跳转 HTTPS？

**A:** 单独 `server { listen 80; server_name seatong.local; return 301 https://$host$request_uri; }`，将所有 HTTP 请求 301 永久跳转 HTTPS，强制加密。

**标签：** 80跳转, listen_80, 301跳转, HTTPS强制, server块

---

## Q: proxy_read_timeout 为何要放大？

**A:** `/api/` 反代设 `proxy_read_timeout 60s;`，避免识别等较慢请求被 Nginx 提前断连（默认超时较短）。后端正常 p50 90.8ms，60s 为充裕余量。

**标签：** proxy_read_timeout, 60s, 反代超时, 识别请求, 断连避免

---

## Q: 多实例负载均衡如何配置？

**A:** 定义 `upstream seatong_backend { server 127.0.0.1:8000; server 127.0.0.1:8001; }`，`location /api/` 的 `proxy_pass http://seatong_backend;`，将请求分发到多个 uvicorn 实例。

**标签：** 负载均衡, upstream, 8000_8001, proxy_pass, 多实例

---

## Q: Nginx 配置校验命令？

**A:** `nginx -t` 校验语法，预期输出 `syntax is ok` / `test is successful`。修改任何配置后必须先 `-t` 再重载，防止错误配置导致启动失败。

**标签：** 配置校验, nginx_t, syntax_ok, test_successful, 必做

---

## Q: Nginx 启动与重载命令？

**A:** 启动：`nginx`（Windows `nginx.exe`）；重载：`nginx -s reload`；停止：`nginx -s stop`。重载不中断服务，适合证书轮换与配置更新。

**标签：** Nginx命令, 启动, reload, stop, 不中断

---

## Q: 配置完成后的验证清单？

**A:** ①`nginx -t` 语法通过；②进程存在；③HTTPS 首页加载；④HTTP 访问 301 跳 HTTPS；⑤`/api/health` 返后端 JSON；⑥刷新二级路由不 404。对照 `deploy/nginx.conf` 验证清单。

**标签：** 验证清单, nginx_t, 首页加载, 301跳转, health

---

## Q: 502 Bad Gateway 的 Nginx 侧原因？

**A:** 访问 `/api` 返回 502，多为后端未起或 `proxy_pass` 不匹配。确认 uvicorn 监听 127.0.0.1:8000，且 `location /api/` 与 `proxy_pass http://127.0.0.1:8000` 斜杠一致。

**标签：** 502, Bad_Gateway, proxy_pass, uvicorn, 斜杠一致

---

## Q: SSL 协议与套件配置建议？

**A:** 参考配置 `ssl_protocols TLSv1.2 TLSv1.3; ssl_ciphers HIGH:!aNULL:!MD5;`，禁用不安全协议与空加密套件，兼顾兼容与安全。

**标签：** SSL协议, TLSv1_2, TLSv1_3, ssl_ciphers, 安全

---

## Q: worker_processes 与连接数？

**A:** 参考配置 `worker_processes 1; events { worker_connections 1024; }`。低并发教学场景足够；生产可按 CPU 核数调 `worker_processes`，连接数按需放大。

**标签：** worker_processes, worker_connections, 1024, CPU核数, 并发

---

## Q: 前端静态目录放哪里？

**A:** 将 `frontend-dist/` 内容复制到 Nginx 站点目录（如 `html/seatong/`），`location /` 的 `root` 指向该目录。验证 `Test-Path html/seatong/index.html` 为 True。

**标签：** 静态目录, frontend-dist, html_seatong, root, index_html

---

## Q: 证书文件路径如何引用？

**A:** `ssl_certificate conf/seatong.crt; ssl_certificate_key conf/seatong.key;`，路径相对 Nginx 前缀或写绝对路径。证书与私钥须匹配且权限受限。

**标签：** 证书路径, ssl_certificate, seatong_crt, seatong_key, 权限

---

## Q: X-Forwarded 头的作用？

**A:** `proxy_set_header X-Real-IP` 与 `X-Forwarded-For/Proto` 将客户端真实 IP 与协议传给后端，便于后端日志、`request_id` 关联与限流（按 `$binary_remote_addr`）正确识别来源。

**标签：** X_Forwarded, X_Real_IP, 真实IP, 日志关联, 限流来源

---

## Q: 上传大图 413 的 Nginx 处理？

**A:** Nginx 在 `client_max_body_size` 超限时直接返回 413，早于后端。设 100m 可容纳单图 10MB/批量 9 张；若仍 413 检查配置所在块（http/server/location）是否生效并已 reload。

**标签：** 413, client_max_body_size, 大图, 100m, reload

---

## Q: 静态图片直出是否走 Nginx？

**A:** 识别图像由后端管理，参考配置注释了可选的 `/api/images/file/` 反代直出；默认经后端 `/api` 反代即可，是否直出按性能需求取舍。

**标签：** 静态图片, images_file, 反代直出, 后端管理, 可选

---

## Q: 多端口负载均衡的 health 检查？

**A:** upstream 多实例（8000/8001）下，仍可用 `/api/health` 验证各实例；Nginx 默认轮询，某实例宕机需配合 `max_fails`/`fail_timeout` 等参数剔除（参考配置未显式配置）。

**标签：** 负载均衡, health, 8000_8001, 轮询, 实例剔除

---

## Q: Nginx 与后端限流如何分工？

**A:** 后端限流 60 次/分钟（42902，业务级，按用户/客户端），Nginx `limit_req` 30r/m+burst 20（网关级，按 IP）。双层互补，Nginx 先拦暴力刷量，后端保业务额度。

**标签：** 限流分工, 60次每分, limit_req, 30r_m, 双层

---

## Q: 证书过期如何轮换？

**A:** 用 openssl 重新生成 `.crt`/`.key` 覆盖原文件，执行 `nginx -s reload` 加载新证书（不中断服务）。自签证书注意 `-days` 有效期，生产 CA 证书按签发机构流程续期。

**标签：** 证书轮换, openssl, reload, 不中断, 有效期

---

## Q: 完整 Nginx 部署步骤回顾？

**A:** ①安装 Nginx 1.24+；②复制 frontend-dist 到站点；③openssl 生成证书；④按 `deploy/nginx.conf` 配 443 ssl/静态/try_files//api 反代/client_max_body_size/limit_req/80 跳转；⑤`nginx -t` 校验；⑥启动并重载；⑦验证清单逐项过。

**标签：** 部署回顾, 安装, 证书, nginx_conf, 校验, 验证

---

## Q: 配置文件位置与维护？

**A:** 主配置参考 `deploy/nginx.conf`（含多端口负载均衡附录）。生产按需调整域名、端口、路径；任何修改先 `nginx -t` 再 `reload`，并留存版本避免误改丢失回退点。

**标签：** 配置位置, deploy_nginx, 附录, nginx_t, 版本留存
