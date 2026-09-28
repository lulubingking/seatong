# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 数据模型（D7 §9.1 DDL 的 SQLAlchemy 实现）

【唯一权威】docs/海瞳鱼鉴-数据库设计文档.md 第 9.1 节「建表语句（DDL 全文）」
本文件逐字对齐该 DDL。凡与 DDL 不符之处，以 DDL 为准。

D7 关键口径（勿凭印象改动）：
  · 7 张表 / 6 个外键 / 10 条显式索引 + 6 条自动索引 = 16
  · 主键类型【不统一】，是有意设计：
      - user / species / operation_log → INTEGER 自增（内部实体，ID 不外露）
      - image_asset / recognition_record → TEXT(36) UUID（对外暴露，需不可枚举）
      - system_config → TEXT 主键 key（配置项天然以 key 标识）
      - guest_usage   → TEXT 主键 session_id
  · 时间字段统一为 INTEGER（Unix 时间戳，UTC），不是 DateTime
  · 布尔/枚举一律 INTEGER + CHECK（SQLite 无原生 BOOLEAN/ENUM）
  · 外键删除策略【方向相反】，务必逐条核对：
      image_asset.user_id            SET NULL   （游客资产无归属；删号后待清理）
      recognition_record.user_id     CASCADE    （记录随账号清理）
      recognition_record.image_id    CASCADE    （原图清理时记录同步移除）
      recognition_record.top1_species_id RESTRICT（基准数据不得删除）
      system_config.updated_by       SET NULL   （保留配置，仅清除修改人）
      operation_log.user_id          SET NULL   （审计日志必须存活）
  · 全部外键 ON UPDATE CASCADE
"""

import time

from sqlalchemy import (
    CheckConstraint, ForeignKey, Index, Integer, REAL, Text, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _ts() -> int:
    """Unix 时间戳（秒，UTC）。D7 决策 4：时间统一用整数而非文本日期。"""
    return int(time.time())


# ==================== 1. user（11 字段） ====================
# DDL：id / username / password_hash / nickname / email / role /
#      status / failed_login_count / locked_until / created_at / updated_at

class User(Base):
    __tablename__ = 'user'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 注意：DDL 的 username 带 UNIQUE，另建 LOWER(username) 函数唯一索引
    # 函数索引在 __table_args__ 里以 text() 声明——SQLAlchemy 的 Index() 不支持表达式
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    nickname: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'user'"))
    # status 用 INTEGER 0/1（1=启用，0=禁用），不是文本
    status: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    # locked_until 存 Unix 时间戳（INTEGER），不是 DateTime
    locked_until: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts, onupdate=_ts)

    records = relationship('RecognitionRecord', back_populates='user')
    assets = relationship('ImageAsset', back_populates='user')
    logs = relationship('OperationLog', back_populates='user')

    __table_args__ = (
        CheckConstraint('length(username) BETWEEN 4 AND 20', name='ck_user_username_len'),
        CheckConstraint("role IN ('user', 'admin')", name='ck_user_role'),
        CheckConstraint('status IN (0, 1)', name='ck_user_status'),
        CheckConstraint('failed_login_count >= 0', name='ck_user_failed_count'),
        # BR-USER-01 要求用户名查重【不区分大小写】。
        # SQLite 的 UNIQUE 按字节比较，'Admin' 与 'admin' 视为不同值，
        # 故必须额外建立函数唯一索引。此索引与列级 UNIQUE 【并存】，不得删除列级 UNIQUE。
        # 表达式索引需 SQLite >= 3.9.0（实测 3.50.4）。
        Index('idx_user_username_lower', text('LOWER(username)'), unique=True),
    )

    # ---- 便捷属性（不映射到列）----
    @property
    def is_active(self) -> bool:
        return self.status == 1

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'


# ==================== 2. image_asset（11 字段） ====================
# DDL：id / user_id / original_filename / stored_path / mime_type / file_size /
#      width / height / content_hash / created_at / expires_at

class ImageAsset(Base):
    __tablename__ = 'image_asset'

    # 【TEXT(36) 主键】对外暴露的 UUID，不可枚举
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # SET NULL：游客上传无归属；账号删除后资产置空等待定期清理
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('user.id', ondelete='SET NULL', onupdate='CASCADE'),
        nullable=True)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 内容 SHA-256，用于重复上传检测
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts)
    expires_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user = relationship('User', back_populates='assets')
    record = relationship('RecognitionRecord', back_populates='image', uselist=False)

    __table_args__ = (
        CheckConstraint('file_size > 0', name='ck_asset_size'),
        Index('idx_image_asset_user_created', 'user_id', text('created_at DESC')),
        Index('idx_image_asset_expires', 'expires_at'),
        Index('idx_image_asset_content_hash', 'content_hash'),
    )


# ==================== 3. recognition_record（13 字段） ====================
# DDL：id / user_id / image_id / top1_species_id / top1_confidence /
#      is_low_confidence / candidates_json / model_version / duration_ms /
#      status / is_deleted / deleted_at / created_at

class RecognitionRecord(Base):
    __tablename__ = 'recognition_record'

    # 【TEXT(36) 主键】与 image_asset 一致，对外暴露
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('user.id', ondelete='CASCADE', onupdate='CASCADE'),
        nullable=False)
    image_id: Mapped[str] = mapped_column(
        Text, ForeignKey('image_asset.id', ondelete='CASCADE', onupdate='CASCADE'),
        nullable=False)
    # RESTRICT：物种是预置基准数据，不允许删除
    top1_species_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('species.id', ondelete='RESTRICT', onupdate='CASCADE'),
        nullable=False)
    top1_confidence: Mapped[float] = mapped_column(REAL, nullable=False)
    is_low_confidence: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    # Top-5 候选 JSON 文本。DDL 用 CHECK(json_valid(...)) 校验。
    # 冗余存 cn_name —— 服务于 BR-HISTORY-09 结果恒定性（决策 2）。
    candidates_json: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'success'"))
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    deleted_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts)

    user = relationship('User', back_populates='records')
    image = relationship('ImageAsset', back_populates='record')
    top1_species = relationship('SpeciesModel')

    __table_args__ = (
        CheckConstraint('top1_confidence BETWEEN 0 AND 1', name='ck_record_conf'),
        CheckConstraint('is_low_confidence IN (0, 1)', name='ck_record_low_conf'),
        CheckConstraint("status IN ('success', 'interrupted')", name='ck_record_status'),
        CheckConstraint('is_deleted IN (0, 1)', name='ck_record_deleted'),
        CheckConstraint('json_valid(candidates_json)', name='ck_record_candidates_json'),
        # 字段顺序不可颠倒：user_id 为等值条件，created_at 为排序键（D7 §4.2）
        Index('idx_record_user_created', 'user_id', text('created_at DESC')),
        Index('idx_record_species', 'top1_species_id'),
        Index('idx_record_deleted', 'is_deleted', 'deleted_at'),
    )


# ==================== 4. species（11 字段） ====================
# DDL：id / class_index / cn_name / latin_name / common_name /
#      morphology / habit / distribution / image_path / created_at / updated_at

class SpeciesModel(Base):
    __tablename__ = 'species'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 对外对齐键：模型输出位次 0～22。id 仅用于数据库内部外键（决策 3）。
    class_index: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    cn_name: Mapped[str] = mapped_column(Text, nullable=False)
    latin_name: Mapped[str] = mapped_column(Text, nullable=False)
    common_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    morphology: Mapped[str] = mapped_column(Text, nullable=False)
    habit: Mapped[str] = mapped_column(Text, nullable=False)
    distribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts, onupdate=_ts)

    __table_args__ = (
        CheckConstraint('class_index BETWEEN 0 AND 22', name='ck_species_index'),
    )


# ==================== 5. system_config（6 字段） ====================
# DDL：key / value / value_type / description / updated_by / updated_at

class SystemConfig(Base):
    __tablename__ = 'system_config'

    # 【TEXT 主键】配置项天然以 key 标识
    # 注意：列名是 key，在 SQLAlchemy 中 key 是保留语义词，故属性名用 config_key 映射
    config_key: Mapped[str] = mapped_column('key', Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('user.id', ondelete='SET NULL', onupdate='CASCADE'),
        nullable=True)
    updated_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint("value_type IN ('int', 'float', 'bool', 'string')",
                        name='ck_config_type'),
    )


# ==================== 6. operation_log（8 字段） ====================
# DDL：id / user_id / action / target_type / target_id / ip / detail / created_at

class OperationLog(Base):
    __tablename__ = 'operation_log'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # SET NULL：审计日志必须存活，即使用户被删（决策 5）。
    # 这与 image_asset / recognition_record 的 CASCADE 策略【相反】。
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey('user.id', ondelete='SET NULL', onupdate='CASCADE'),
        nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts)

    user = relationship('User', back_populates='logs')

    __table_args__ = (
        CheckConstraint(
            "action IN ('login', 'logout', 'upload', 'recognize', 'export', "
            "'delete', 'config_update', 'user_disable', 'password_reset')",
            name='ck_log_action'),
        Index('idx_log_user_created', 'user_id', text('created_at DESC')),
        Index('idx_log_action_created', 'action', text('created_at DESC')),
    )


# ==================== 7. guest_usage（4 字段） ====================
# DDL：session_id / usage_count / first_seen_at / last_seen_at

class GuestUsage(Base):
    __tablename__ = 'guest_usage'

    # 【TEXT 主键】游客会话标识，存于前端 localStorage，用于额度统计
    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    first_seen_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts)
    last_seen_at: Mapped[int] = mapped_column(Integer, nullable=False, default=_ts)

    __table_args__ = (
        CheckConstraint('usage_count >= 0', name='ck_guest_count'),
        Index('idx_guest_last_seen', 'last_seen_at'),
    )


# ==================== 操作日志动作常量（与 CHECK 约束同源） ====================

LOG_ACTIONS = ('login', 'logout', 'upload', 'recognize', 'export',
               'delete', 'config_update', 'user_disable', 'password_reset')


__all__ = ['User', 'ImageAsset', 'RecognitionRecord', 'SpeciesModel',
           'SystemConfig', 'OperationLog', 'GuestUsage', 'LOG_ACTIONS']
