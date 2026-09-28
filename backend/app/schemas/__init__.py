# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · Pydantic 数据契约（对应 D8 API 接口契约）

分组与 D8 第 3～10 章一致：
  · 通用        —— 统一响应体包装
  · 认证 auth   —— 注册/登录/刷新/登出
  · 用户 users  —— 当前用户、改密、管理端用户 CRUD
  · 图像 images —— 上传
  · 识别 recognize —— 推理
  · 结果 result —— 识别结果详情与 Top-5
  · 历史 history —— 列表、详情、删除、导出
  · 物种 species —— 物种介绍
  · 系统 admin  —— 配置、日志、统计

字段命名对齐 D7：cn_name / latin_name（非 species_name / sci_name）。
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ==================== 通用 ====================

class Envelope(BaseModel):
    """统一响应体（PRD §8.3.1）。

    { "code": 0, "message": "ok", "data": {...}, "request_id": "..." }
    """
    code: int = 0
    message: str = 'ok'
    data: Any = None
    request_id: str = ''


class PageMeta(BaseModel):
    page: int = 1
    page_size: int = 20
    total: int = 0
    total_pages: int = 0


# ==================== 认证 ====================

class RegisterIn(BaseModel):
    username: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=8, max_length=64)
    nickname: str = Field(default='', max_length=20)
    email: str | None = Field(default=None, max_length=120)

    @field_validator('username')
    @classmethod
    def _username_charset(cls, v: str) -> str:
        if not all(c.isalnum() or c == '_' for c in v):
            raise ValueError('用户名只能包含字母、数字与下划线')
        return v


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=64)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'
    expires_in: int          # 秒
    user: 'UserOut'


# ==================== 用户 ====================

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str
    email: str | None = None
    role: Literal['user', 'admin']
    status: int = 1
    created_at: int


class UserMeOut(BaseModel):
    user: UserOut | None = None
    is_guest: bool = False
    guest_quota: dict | None = None


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=8, max_length=64)


class AdminUserCreateIn(BaseModel):
    username: str = Field(min_length=4, max_length=20)
    password: str = Field(min_length=8, max_length=64)
    nickname: str = Field(default='', max_length=20)
    email: str | None = Field(default=None, max_length=120)
    role: Literal['user', 'admin'] = 'user'


class AdminUserUpdateIn(BaseModel):
    nickname: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=120)
    role: Literal['user', 'admin'] | None = None
    status: int | None = None


class AdminResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=64)


# ==================== 图像 ====================

class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    mime_type: str
    file_size: int
    width: int | None = None
    height: int | None = None
    content_hash: str | None = None
    created_at: int
    expires_at: int | None = None


class UploadOut(BaseModel):
    """上传响应。注意：上传【不消耗】游客额度。"""
    image: ImageOut
    reused: bool = False       # content_hash 命中已存在资产时为 True


# ==================== 识别 ====================

class RecognizeIn(BaseModel):
    image_id: str
    top_k: int = Field(default=5, ge=1, le=23)


class BatchRecognizeIn(BaseModel):
    """批量识别入参（PRD FR-RECOG-05）。

    上限与批量上传一致（settings.batch_upload_limit = 9），
    避免"能上传却识别不了"的不一致体验。
    """
    image_ids: list[str] = Field(min_length=1, max_length=9)
    top_k: int = Field(default=5, ge=1, le=23)


class CandidateOut(BaseModel):
    rank: int
    class_index: int
    cn_name: str
    latin_name: str
    confidence: float


class SpeciesBriefOut(BaseModel):
    class_index: int
    cn_name: str
    latin_name: str
    common_name: str | None = None
    morphology: str = ''
    habit: str = ''
    distribution: str | None = None
    image_path: str | None = None


class RecognizeOut(BaseModel):
    record_id: str | None = None
    image: ImageOut
    class_index: int
    cn_name: str
    latin_name: str
    confidence: float
    is_low_confidence: bool = False
    candidates: list[CandidateOut] = []
    species: SpeciesBriefOut | None = None
    duration_ms: int
    model_version: str
    guest_quota: dict | None = None   # 游客返回剩余额度


# ==================== 历史 ====================

class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    class_index: int
    cn_name: str
    latin_name: str
    confidence: float
    is_low_confidence: bool = False
    duration_ms: int
    status: str
    created_at: int
    image_id: str
    thumb_url: str = ''


class RecordDetailOut(BaseModel):
    record: RecordOut
    candidates: list[CandidateOut] = []
    species: SpeciesBriefOut | None = None
    image: ImageOut | None = None


class RecordDeleteIn(BaseModel):
    record_ids: list[str] = Field(min_length=1)


# ==================== 物种 ====================

class SpeciesListOut(BaseModel):
    total: int
    items: list[SpeciesBriefOut]


# ==================== 系统 / 管理 ====================

class ConfigItemOut(BaseModel):
    config_key: str
    value: str
    value_type: str
    description: str | None = None
    updated_at: int | None = None


class ConfigUpdateIn(BaseModel):
    value: str


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    ip: str | None = None
    detail: str | None = None
    created_at: int


class StatsOut(BaseModel):
    total_users: int
    active_users: int
    total_records: int
    total_uploads: int
    records_today: int
    top_species: list[dict] = []
    avg_duration_ms: float = 0.0


TokenOut.model_rebuild()


__all__ = [
    'Envelope', 'PageMeta',
    'RegisterIn', 'LoginIn', 'RefreshIn', 'TokenOut',
    'UserOut', 'UserMeOut', 'ChangePasswordIn',
    'AdminUserCreateIn', 'AdminUserUpdateIn', 'AdminResetPasswordIn',
    'ImageOut', 'UploadOut',
    'RecognizeIn', 'RecognizeOut', 'CandidateOut', 'SpeciesBriefOut',
    'BatchRecognizeIn',
    'RecordOut', 'RecordDetailOut', 'RecordDeleteIn',
    'SpeciesListOut',
    'ConfigItemOut', 'ConfigUpdateIn', 'LogOut', 'StatsOut',
]
