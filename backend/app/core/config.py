# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 后端配置

环境变量前缀 `SEATONG_`（PRD §8.5 联调约定）。
所有配置项均可被同名环境变量覆盖，便于部署时调整。
"""

import os
import sys
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# 【可移植性说明】原实现把 ROOT 硬编码为开发机绝对路径（E:\...），
# 克隆到其他目录即失效。现按以下优先级解析：
#   1) 环境变量 SEATONG_ROOT（部署时把数据/模型放到仓库外时用）；
#   2) 由本文件位置向上三级推导：<ROOT>/backend/app/core/config.py
#      → dirname×3 = <ROOT>，与磁盘位置无关。
# 目标：克隆到任意路径、任意盘符均可直接启动。

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(os.path.dirname(_CORE_DIR))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)

ROOT = os.environ.get('SEATONG_ROOT') or _REPO_ROOT
BACKEND = os.environ.get('SEATONG_BACKEND_DIR') or _BACKEND_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='SEATONG_',
        env_file=os.path.join(BACKEND, '.env'),
        env_file_encoding='utf-8',
        extra='ignore',
    )

    # ---- 应用 ----
    app_name: str = '海瞳鱼鉴 SeaPupil'
    app_version: str = '1.0.0'
    debug: bool = True
    api_prefix: str = '/api'

    # ---- 服务 ----
    host: str = '0.0.0.0'
    port: int = 8000
    # 前端 dev server 端口为 5180（非 Vite 默认 5173：5173 被同机另一项目占用）。
    # 与 frontend/vite.config.ts 的 server.port 及 route-smoke.mjs 默认基址保持一致。
    frontend_origin: str = 'http://localhost:5180'

    # ---- 数据库 ----
    db_path: str = os.path.join(BACKEND, 'data', 'seatong.db')

    # ---- 安全 ----
    jwt_secret: str = 'seatong-dev-secret-change-in-production'
    jwt_algorithm: str = 'HS256'
    access_token_expire_minutes: int = 120       # 短期令牌（PRD 决策基线）
    refresh_token_expire_days: int = 7
    bcrypt_rounds: int = 12

    # 登录失败锁定（对应错误码 40105）
    login_max_failures: int = 5
    login_lock_minutes: int = 15

    # ---- 游客额度（PRD 决策基线：免登录试用 3 次） ----
    guest_quota: int = 3

    # ---- 上传限制（PRD §8.4） ----
    max_file_size_mb: int = 10
    batch_upload_limit: int = 9
    allowed_extensions: str = 'png,jpg,jpeg,bmp'
    image_retention_days: int = 180
    image_storage_dir: str = os.path.join(BACKEND, 'storage', 'images')

    # ---- 识别 ----
    # 主模型：M1_ood_tuned（M1_main_224 出发 + 307 张网图混合微调 4 轮）。
    # 双门槛验收通过：网图 OOD Top-1 32.26%→82.80%（+50.5pp），
    # 同分布测试 acc 0.9960（-0.03pp）/ macro_f1 0.9694（+0.16pp），无遗忘。
    # 详见 ml/models/M1_ood_tuned/finetune_report.json 与 docs/海瞳鱼鉴-分布外网图评估报告.md
    # 可通过环境变量 SEATONG_MODEL_PATH 指向其他实验产物（如 M1_main_224 基线）
    model_path: str = os.path.join(ROOT, 'ml', 'models', 'M1_ood_tuned', 'best.pt')
    model_classes_file: str = os.path.join(ROOT, 'ml', 'dataset', 'classes.txt')
    infer_timeout_ms: int = 2000
    max_concurrent_infer: int = 3

    # ---- 限流（对应 42902） ----
    rate_limit_per_minute: int = 60

    # ---- 日志 ----
    log_dir: str = os.path.join(BACKEND, 'logs')
    log_level: str = 'INFO'

    # ---- 派生属性 ----
    @property
    def allowed_ext_list(self) -> list[str]:
        return [e.strip().lower().lstrip('.') for e in self.allowed_extensions.split(',') if e.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def ensure_backend_dirs() -> None:
    for d in (os.path.dirname(settings.db_path), settings.image_storage_dir, settings.log_dir):
        os.makedirs(d, exist_ok=True)


if __name__ == '__main__':
    ensure_backend_dirs()
    s = get_settings()
    print('后端配置')
    for k in ('app_name', 'app_version', 'host', 'port', 'api_prefix', 'frontend_origin'):
        print(f'  {k:26s} {getattr(s, k)}')
    print(f'  {"db_path":26s} {s.db_path}')
    print(f'  {"image_storage_dir":26s} {s.image_storage_dir}')
    print(f'  {"max_file_size_mb":26s} {s.max_file_size_mb}')
    print(f'  {"batch_upload_limit":26s} {s.batch_upload_limit}')
    print(f'  {"allowed_ext_list":26s} {s.allowed_ext_list}')
    print(f'  {"guest_quota":26s} {s.guest_quota}')
    print(f'  {"access_token_expire_min":26s} {s.access_token_expire_minutes}')
    print(f'  {"model_path":26s} {s.model_path}')
    print(f'  {"model exists":26s} {os.path.exists(s.model_path)}')
