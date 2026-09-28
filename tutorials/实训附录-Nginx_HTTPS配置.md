# 实训附录 海瞳鱼鉴 Nginx HTTPS 配置

## 一、实训目标

1. 掌握 Windows 下 Nginx 的安装与基础运维命令
2. 学会使用 OpenSSL 生成自签名 SSL 证书并配置 HTTPS
3. 理解反向代理原理，配置 Nginx 托管前端静态资源并将 `/api` 转发至后端
4. 掌握 SPA 路由回退（`try_files`）与上传体积上限（`client_max_body_size`）的配置
5. 能够实现 HTTP 80 到 HTTPS 443 的强制跳转并完成整体验收

## 二、实训内容

### 1. 背景知识

浏览器安全策略要求使用上传的网页必须通过 HTTPS 访问。海瞳鱼鉴生产部署采用 **Nginx 反向代理 + HTTPS** 形态：

- **前端**：`frontend-dist/`（即 `npm run build` 产物）由 Nginx 静态托管
- **后端**：uvicorn 运行于 127.0.0.1:8000（仅内网），Nginx 将 `/api` 反向代理至后端
- **数据库**：SQLite 单文件，首次部署由 `scripts/init_db.py` 初始化

网络架构：

```
用户浏览器 → https://seatong.local → Nginx(443)
                    ↓
            ┌───────┴───────┐
            ↓               ↓
    前端静态(index.html)  API 请求(/api/*)
            ↓               ↓
    html/seatong/      反向代理 127.0.0.1:8000
```

### 2. 部署形态

| 组件 | 端口 | 说明 |
| --- | --- | --- |
| Nginx | 443（HTTPS）/ 80（跳转） | 对外入口，托管前端静态资源 |
| 后端 uvicorn | 8000（仅内网） | API 前缀 `/api` |
| SQLite | - | 本地文件存储，7 表 64 字段 |

### 3. 参考配置来源

本实训片段来自交付包 `部署版code\seatong\deploy\nginx.conf`，与《海瞳鱼鉴生产部署文档》（README_prod.md）一致。

## 三、实训步骤

### 步骤 1：安装 Nginx（Windows）

**操作命令：**

```powershell
# 从 https://nginx.org/en/download.html 下载 Windows 版（如 nginx/Windows-1.24.x）
# 解压到 C:\nginx（保持 C:\nginx\conf\、html\、logs\ 结构）
C:\nginx\nginx.exe -v
```

**验证方法：**

```powershell
C:\nginx\nginx.exe -v
# 预期输出: nginx version: nginx/1.24.x
```

**成功标志：** `C:\nginx` 目录存在，`nginx.exe` 可运行，`nginx -v` 显示版本号。

### 步骤 2：准备前端静态资源与站点目录

**操作命令：**

```powershell
New-Item -ItemType Directory -Force -Path "C:\nginx\html\seatong" | Out-Null
Copy-Item -Recurse "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\部署版code\seatong\frontend-dist\*" "C:\nginx\html\seatong\"
```

**验证方法：**

```powershell
Test-Path "C:\nginx\html\seatong\index.html"
# 预期输出: True
```

**成功标志：** `C:\nginx\html\seatong\index.html` 存在，前端资源已完整复制。

### 步骤 3：生成自签名 SSL 证书（OpenSSL）

**操作命令：**

```powershell
openssl req -x509 -nodes -days 365 -newkey rsa:2048 `
  -keyout "C:\nginx\conf\seatong.key" `
  -out "C:\nginx\conf\seatong.crt" `
  -subj "/CN=seatong.local"
```

**验证方法：**

```powershell
Test-Path "C:\nginx\conf\seatong.crt"; Test-Path "C:\nginx\conf\seatong.key"
# 预期输出: 两次均为 True
```

**成功标志：** `C:\nginx\conf\seatong.crt` 与 `seatong.key` 已生成，subject 为 `/CN=seatong.local`。

### 步骤 4：编写并应用 nginx.conf

将以下内容写入 `C:\nginx\conf\nginx.conf`（参考 `deploy/nginx.conf`）：

```nginx
worker_processes  1;

events {
    worker_connections  1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout  65;

    # 上传体积上限：单图 <=10MB、批量 <=9 张，预留余量
    client_max_body_size 100m;

    # HTTP -> HTTPS 强制跳转
    server {
        listen      80;
        server_name seatong.local;
        return 301  https://$host$request_uri;
    }

    # HTTPS 主站
    server {
        listen      443 ssl;
        server_name seatong.local;

        ssl_certificate      conf/seatong.crt;
        ssl_certificate_key  conf/seatong.key;
        ssl_protocols        TLSv1.2 TLSv1.3;
        ssl_ciphers          HIGH:!aNULL:!MD5;

        # 前端静态资源（frontend-dist 构建产物）
        location / {
            root   html/seatong;
            index  index.html;
            try_files $uri $uri/ /index.html;   # SPA 路由回退
        }

        # 后端 API 反向代理
        location /api/ {
            proxy_pass         http://127.0.0.1:8000;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header   X-Forwarded-Proto $scheme;
            proxy_read_timeout 60s;
        }
    }
}
```

**验证方法：**

```powershell
C:\nginx\nginx.exe -t
# 预期输出: nginx: the configuration file ... syntax is ok
#           nginx: configuration file ... test is successful
```

**成功标志：** `nginx -t` 报告 `syntax is ok` 与 `test is successful`；配置含 `client_max_body_size 100m`、`try_files ... /index.html`、`proxy_pass http://127.0.0.1:8000`。

### 步骤 5：启动后端并启动 Nginx

**操作命令：**

```powershell
# 后端（仅内网监听）
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\部署版code\seatong\backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 启动 Nginx（另开终端）
C:\nginx\nginx.exe
```

**验证方法：**

```powershell
Get-Process -Name nginx | Select-Object -First 1
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -Method GET
# 预期输出: 显示 nginx 进程；返回健康检查 JSON
```

**成功标志：** 存在 nginx 进程；后端健康检查正常。

### 步骤 6：验证 HTTPS 访问与跳转

**操作命令：**

```powershell
Invoke-WebRequest -Uri "https://seatong.local" -SkipCertificateCheck | Select-Object StatusCode
Invoke-WebRequest -Uri "http://seatong.local" -SkipCertificateCheck -MaximumRedirection 0 -ErrorAction SilentlyContinue | Select-Object StatusCode
Invoke-RestMethod -Uri "https://seatong.local/api/health" -SkipCertificateCheck -Method GET
```

> 若浏览器打不开 `seatong.local`，在本机 `C:\Windows\System32\drivers\etc\hosts` 增加 `127.0.0.1 seatong.local`（需管理员权限）。

**验证方法：**

```powershell
# 预期：首页 200、HTTP 301 跳转、/api/health 经 Nginx 返回后端 JSON
```

**成功标志：** HTTPS 首页返回 200，HTTP 返回 301 并跳转 HTTPS，`/api/health` 经反代返回后端 JSON。

### 步骤 7：整体验收（识别 + 历史 + 导出）

**验证方法：**

```powershell
# 浏览器打开 https://seatong.local/ ，预期加载首页（锁形图标，无混合内容告警）
# 上传图片执行识别，预期返回 Top-1 物种 + 置信度 + Top-5 候选
# 注册/登录、历史记录、CSV 导出、后台管理逐项验证
```

**成功标志：** 首页正常；识别接口返回 Top-1 + Top-5 候选；历史、导出、后台管理可用。

## 四、验证清单

| 验证项 | 验证方法 | 预期结果 |
|--------|----------|----------|
| Nginx 安装 | `nginx.exe -v` | 显示版本 |
| 前端资源 | `Test-Path html/seatong/index.html` | True |
| 证书生成 | `Test-Path conf/seatong.crt` | True |
| 配置语法 | `nginx.exe -t` | syntax is ok / test successful |
| 服务进程 | `Get-Process nginx` | 进程存在 |
| 后端可达 | `/api/health` 直连 8000 | 返回 JSON |
| HTTPS 访问 | 浏览器 https://域名 | 首页加载 |
| HTTP 跳转 | 访问 http://域名 | 301 跳转 HTTPS |
| API 代理 | 访问 /api/health | 返回后端 JSON |
| SPA 回退 | 刷新二级路由 | 正常渲染不 404 |
| 上传上限 | 上传大图（<100m） | 成功；超 100m 返回 413 |

## 五、故障排除

### 问题 1：Nginx 启动报 502 Bad Gateway

**解决方案：**

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
# 预期输出: 显示 LISTENING；检查 proxy_pass 末尾斜杠与 /api/ 匹配关系
```

### 问题 2：上传大图失败（413 Request Entity Too Large）

**解决方案：**

```powershell
# 在 http 或 server 块确保设置 client_max_body_size 100m; 后重载
C:\nginx\nginx.exe -s reload
```

### 问题 3：前端刷新二级路由返回 404

**解决方案：**

```powershell
# 确认 location / 配置了 try_files $uri $uri/ /index.html; 后 reload
C:\nginx\nginx.exe -s reload
```

### 问题 4：浏览器提示证书不受信任

**解决方案：** 自签证书仅用于内网/教学，需手动信任：将 `C:\nginx\conf\seatong.crt` 导入"受信任的根证书颁发机构"，或访问时点击"高级 → 继续前往"；生产环境改用受信任 CA 证书。

### 问题 5：域名无法解析（seatong.local 打不开）

**解决方案：**

```powershell
# 以管理员身份运行 PowerShell
Add-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value "127.0.0.1 seatong.local"
```

## 六、参考代码

### 完整目录结构

```
C:\nginx\
├── conf\{nginx.conf, seatong.crt, seatong.key}
├── html\seatong\{index.html, assets\}
└── logs\

E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\部署版code\seatong\
├── frontend-dist\          # 前端生产构建
├── backend\                # uvicorn 8000
└── deploy\nginx.conf       # 参考配置
```

### 常用命令

```powershell
C:\nginx\nginx.exe -t          # 校验配置
C:\nginx\nginx.exe             # 启动
C:\nginx\nginx.exe -s reload   # 重载
C:\nginx\nginx.exe -s stop     # 停止

# 启动后端
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\部署版code\seatong\backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 关键配置说明

| 指令 | 位置 | 说明 | 示例 |
|------|------|------|------|
| `client_max_body_size` | http/server | 上传体积上限 | 100m |
| `listen 443 ssl` | server | HTTPS 监听 | 443 |
| `ssl_certificate` | server | 证书路径 | conf/seatong.crt |
| `ssl_certificate_key` | server | 私钥路径 | conf/seatong.key |
| `try_files` | location / | SPA 路由回退 | `$uri $uri/ /index.html` |
| `proxy_pass` | location /api/ | 后端反代 | http://127.0.0.1:8000 |
| `return 301` | server(80) | HTTP→HTTPS 跳转 | `https://$host$request_uri` |

### 部署安全要点（来自 README_prod.md）

1. 后端不直连公网：仅 Nginx 对外，后端绑定 127.0.0.1
2. HTTPS 强制：HTTP 全部 301 跳转；生产使用受信任 CA 证书
3. 限流保护：后端内置 60 次/分钟限流（42902），Nginx 可叠加 `limit_req`
4. 数据备份：定期备份 `seatong.db` 与 `backend/storage/images/`
5. 环境变量：模型路径等通过 `SEATONG_` 前缀注入，勿写入代码
