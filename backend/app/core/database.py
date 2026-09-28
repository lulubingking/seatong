# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 数据库引擎与会话（SQLite）

D7 关键口径：
  · SQLite 无原生 ENUM/布尔 → 用 TEXT/INTEGER + CHECK 约束
  · `PRAGMA foreign_keys` 默认 OFF → 【必须每连接显式开启】
  · WAL 模式提升并发读性能
  · 表达式索引需 SQLite ≥3.9.0
"""

import sqlite3
import sys
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings, ensure_backend_dirs  # noqa: E402

class Base(DeclarativeBase):
    pass


ensure_backend_dirs()

DB_URL = f'sqlite:///{settings.db_path}'

engine = create_engine(
    DB_URL,
    echo=False,
    future=True,
    connect_args={
        'check_same_thread': False,   # FastAPI 多线程
        'timeout': 15,
    },
)


@event.listens_for(engine, 'connect')
def _on_connect(dbapi_conn, conn_record):
    """每个新连接都要设的 PRAGMA —— 尤其 foreign_keys，默认是 OFF！"""
    cur = dbapi_conn.cursor()
    cur.execute('PRAGMA foreign_keys=ON')
    cur.execute('PRAGMA journal_mode=WAL')
    cur.execute('PRAGMA synchronous=NORMAL')
    cur.execute('PRAGMA busy_timeout=15000')
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db():
    """FastAPI 依赖注入用。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def sqlite_version() -> str:
    return sqlite3.sqlite_version


def pragma_report() -> dict:
    """体检：确认关键 PRAGMA 生效。"""
    out = {}
    with engine.connect() as conn:
        from sqlalchemy import text
        for p in ('foreign_keys', 'journal_mode', 'synchronous', 'busy_timeout'):
            try:
                out[p] = conn.execute(text(f'PRAGMA {p}')).scalar()
            except Exception as e:
                out[p] = f'ERR {e}'
    return out


if __name__ == '__main__':
    # 【注意】不要在此处写建表逻辑。
    # 以脚本方式运行本文件时，app.models 里的 `from app.core.database import Base`
    # 会再导入一份 app.core.database，导致内存中出现两个不同的 Base 类，
    # 本文件的 Base.metadata 永远为空。
    # 初始化与体检请用：python backend/scripts/init_db.py
    print(__doc__)
    print('请改用入口脚本：python backend/scripts/init_db.py')

