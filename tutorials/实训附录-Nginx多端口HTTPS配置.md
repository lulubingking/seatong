# 实训附录 海瞳鱼鉴 Nginx 多端口 HTTPS 配置

## 一、实训目标

1. 理解多实例负载均衡的意义，能够启动多个 uvicorn 实例（8000 / 8001）
2. 掌握 Nginx `upstream` 模块配置，将请求在多个后端实例间分发
3. 能够在 HTTPS 前提下复用前端静态托管与 `/api` 反代，并把 `proxy_pass` 指向 upstream
4. 掌握负载均衡的验证方法（轮询分发、实例宕机自动剔除）
5. 能够结合单端口 HTTPS 配置完成整体验收

## 二、实训内容

### 1. 背景知识

单实例 uvicorn（8000）在并发识别请求增加时可能成为瓶颈。启动多个 uvicorn 实例，再用 Nginx 的 `upstream` 做反向代理层负载均衡，可以：

- 提升并发吞吐（请求在 8000 / 8001 间轮询分发）
- 实现高可用（某实例宕机时 Nginx 自动将流量切到存活实例）
- 支持灰度发布（先停旧实例、再起新实例）

本实训基于交付包 `部署版code\seatong\deploy\nginx.conf` 的"多端口负载均衡版"片段扩展，该片段定义了 `upstream seatong_backend`：

```nginx
upstream seatong_backend {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;
}
```

### 2. 网络架构

```
用户浏览器 → https://seatong.local → Nginx(443)
                    ↓
              upstream seatong_backend
            ┌───────┴───────┐
            ↓               ↓
     uvicorn :8000    uvicorn :8001
```

### 3. 部署形态对照

| 形态 | 后端实例 | proxy_pass 目标 |
| --- | --- | --- |
| 单端口（附录前文） | 1 个（8000） | http://127.0.0.1:8000 |
| 多端口（本实训） | 2 个（8000 / 8001） | http://seatong_backend |

## 三、实训步骤

### 步骤 1：启动两个 uvicorn 后端实例

**操作命令：**

```powershell
# 实例 1（8000）
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\部署版code\seatong\backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 另开终端，实例 2（8001）
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\部署版code\seatong\backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

**验证方法：**

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
# 预期输出: 两者均显示 LISTENING
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -Method GET
Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/health" -Method GET
# 预期输出: 两个端口均返回健康检查 JSON
```

**成功标志：** 8000 与 8001 均 LISTENING，两实例 `/api/health` 均正常返回。

### 步骤 2：配置自签名证书（若尚未生成）

**操作命令：**

```powershell
openssl req -x509 -nodes -days 365 -newkey rsa:2048 `
  -keyout "C:\nginx\conf\seatong.key" `
  -out "C:\nginx\conf\seatong.crt" `
  -subj "/CN=seatong.local"
Test-Path "C:\nginx\conf\seatong.crt"
# 预期输出: True
```

**成功标志：** 证书与私钥已存在于 `C:\nginx\conf\`。

### 步骤 3：编写多端口 upstream 配置

将以下内容写入 `C:\nginx\conf\nginx.conf`（http 块内定义 upstream，server 块引用）：

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

    client_max_body_size 100m;

    # 多 uvicorn 实例负载均衡
    upstream seatong_backend {
        server 127.0.0.1:8000;
        server 127.0.0.1:8001;
    }

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
            try_files $uri $uri/ /index.html;
        }

        # 后端 API 反向代理（指向 upstream）
        location /api/ {
            proxy_pass         http://seatong_backend;
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
# 预期输出: syntax is ok / test is successful
```

**成功标志：** `nginx -t` 通过；配置含 `upstream seatong_backend`（两个 server）且 `proxy_pass http://seatong_backend;`。

### 步骤 4：启动 / 重载 Nginx

**操作命令：**

```powershell
C:\nginx\nginx.exe -t
C:\nginx\nginx.exe -s reload
# 首次启动用：
C:\nginx\nginx.exe
```

**验证方法：**

```powershell
Get-Process -Name nginx | Select-Object -First 1
# 预期输出: 显示 nginx 进程
```

**成功标志：** nginx 进程存在，配置已应用（reload 无报错）。

### 步骤 5：验证负载均衡分发

**操作命令：**

```powershell
1..6 | ForEach-Object {
    Invoke-RestMethod -Uri "https://seatong.local/api/health" -SkipCertificateCheck -Method GET
}
```

**验证方法：**

```powershell
# 临时停掉 8001 实例（Ctrl+C），再请求
Invoke-RestMethod -Uri "https://seatong.local/api/health" -SkipCertificateCheck -Method GET
# 预期输出: 仍返回 200（Nginx 自动剔除宕机实例）
```

**成功标志：** 多次请求轮询分发到 8000 / 8001；一实例宕机时自动转发至存活实例，服务不中断。

### 步骤 6：整体验收（HTTPS + 多实例）

**操作命令：**

```powershell
Invoke-WebRequest -Uri "https://seatong.local" -SkipCertificateCheck | Select-Object StatusCode
Invoke-RestMethod -Uri "https://seatong.local/api/health" -SkipCertificateCheck -Method GET
```

**验证方法：**

```powershell
# 浏览器打开 https://seatong.local/ ，上传鱼类图片执行识别
# 预期：经负载均衡分发到 8000/8001，返回 Top-1 + Top-5 候选
```

**成功标志：** HTTPS 首页 200，HTTP 301 跳转；`/api` 经 upstream 反代正常；识别功能在多实例下可用。

## 四、验证清单

| 验证项 | 验证方法 | 预期结果 |
|--------|----------|----------|
| 实例 8000 | `Get-NetTCPConnection -LocalPort 8000` | LISTENING |
| 实例 8001 | `Get-NetTCPConnection -LocalPort 8001` | LISTENING |
| 双实例健康 | 分别 `/api/health` | 均返回 JSON |
| upstream 配置 | `nginx.exe -t` | syntax is ok |
| proxy_pass 指向 | `Select-String nginx.conf "seatong_backend"` | 命中 upstream 与 proxy_pass |
| Nginx 进程 | `Get-Process nginx` | 进程存在 |
| 负载分发 | 多次请求观察实例 | 轮询到 8000/8001 |
| 故障转移 | 停一实例再请求 | 仍 200 |
| HTTPS 访问 | 浏览器 https://域名 | 首页加载 |
| HTTP 跳转 | http://域名 | 301 跳转 |

## 五、故障排除

### 问题 1：Nginx 报 `no live upstreams`

**解决方案：**

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue
# 若有实例未启动，重新拉起；Nginx 仅在至少有一个存活实例时才正常
```

### 问题 2：所有流量只打到 8000，未轮询

**解决方案：**

```powershell
Select-String -Path "C:\nginx\conf\nginx.conf" -Pattern "upstream|server 127.0.0.1:800"
# 预期输出: 含 seatong_backend 及 8000/8001 两行
# 默认轮询（round-robin）；server 后可加 weight 调整权重
```

### 问题 3：reload 后仍走旧配置

**解决方案：**

```powershell
C:\nginx\nginx.exe -t
C:\nginx\nginx.exe -s reload
# 若仍异常：先 stop 再启动以强制重新加载
C:\nginx\nginx.exe -s stop
C:\nginx\nginx.exe
```

### 问题 4：HTTPS 证书报错

**解决方案：** 自签证书需手动信任，或将 `conf/seatong.crt` 导入"受信任的根证书颁发机构"；脚本请求可加 `-SkipCertificateCheck`。

### 问题 5：两个实例共享 SQLite 写入冲突

**解决方案：** SQLite 为单文件，多实例并发写需控制连接与超时（WAL 模式 + busy_timeout）；或改用量级更大的数据库（如 PostgreSQL）；教学环境建议控制并发或单写多读。

## 六、参考代码

### 常用命令

```powershell
# 启动两个后端实例
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\部署版code\seatong\backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Nginx 运维
C:\nginx\nginx.exe -t
C:\nginx\nginx.exe -s reload
C:\nginx\nginx.exe -s stop
C:\nginx\nginx.exe
```

