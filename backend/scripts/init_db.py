# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 数据库初始化与体检

【为什么不写在 database.py 的 __main__ 里】
以脚本方式运行 `python app/core/database.py` 时，该文件成为 __main__ 模块，
而 app/models 里的 `from app.core.database import Base` 会再导入一份
app.core.database —— 于是内存中存在【两个不同的 Base 类】，
__main__ 里的 Base.metadata 永远是空的。
用独立入口脚本从 app.* 正规导入，只存在唯一一份 Base。

体检口径全部取自 D7：
  · 7 张表 · 6 个外键 · 10 条显式索引 + 6 条自动索引 = 16
  · 字段总数 64（11+11+13+11+6+8+4）
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from sqlalchemy import inspect        # noqa: E402

from app.core.config import ensure_backend_dirs, settings              # noqa: E402
from app.core.database import Base, engine, pragma_report, sqlite_version  # noqa: E402
import app.models as models          # noqa: E402

# D7 权威口径
EXPECT_FIELDS = {
    'user': 11, 'image_asset': 11, 'recognition_record': 13, 'species': 11,
    'system_config': 6, 'operation_log': 8, 'guest_usage': 4,
}
EXPECT_EXPLICIT_IDX = {
    'user': 1,               # idx_user_username_lower
    'image_asset': 3,        # user_created / expires / content_hash
    'recognition_record': 3, # user_created / species / deleted
    'species': 0,            # class_index 走列级 UNIQUE（自动索引）
    'system_config': 0,
    'operation_log': 2,      # user_created / action_created
    'guest_usage': 1,        # last_seen
}
EXPECT_FK = {
    'image_asset': 1, 'recognition_record': 3, 'system_config': 1,
    'operation_log': 1, 'user': 0, 'species': 0, 'guest_usage': 0,
}
# 6 个外键的删除策略（方向相反，务必逐条）
EXPECT_FK_ONDELETE = {
    ('image_asset', 'user_id'): 'SET NULL',
    ('recognition_record', 'user_id'): 'CASCADE',
    ('recognition_record', 'image_id'): 'CASCADE',
    ('recognition_record', 'top1_species_id'): 'RESTRICT',
    ('system_config', 'updated_by'): 'SET NULL',
    ('operation_log', 'user_id'): 'SET NULL',
}


def main() -> int:
    ensure_backend_dirs()
    problems: list[str] = []

    print('=' * 74)
    print('海瞳鱼鉴 · 数据库初始化与体检')
    print('=' * 74)
    print(f'  SQLite 版本      {sqlite_version()}   (表达式索引需 ≥3.9.0)')
    print(f'  数据库路径       {settings.db_path}')
    print()

    n_meta = len(Base.metadata.tables)
    print(f'  模型已注册表数   {n_meta}  （期望 7）')
    if n_meta != 7:
        print('  ✗ 模型注册异常，中止')
        return 2

    Base.metadata.create_all(engine)

    # ---- PRAGMA ----
    print()
    print('  PRAGMA 体检（关键：foreign_keys 必须为 1）')
    for k, v in pragma_report().items():
        flag = ''
        if k == 'foreign_keys':
            if v == 1:
                flag = '  ✓ 已开启（关键）'
            else:
                flag = '  ✗ 未开启 —— 严重问题！'
                problems.append('foreign_keys 未开启')
        print(f'    {k:16s} {v}{flag}')

    insp = inspect(engine)
    tabs = sorted(insp.get_table_names())

    # ---- 索引：直查 sqlite_master ----
    # 【为什么不用 inspector.get_indexes()】
    # SQLAlchemy 的 inspector 无法反射"表达式索引"（如 LOWER(username)），
    # 会静默跳过并只发 SAWarning —— 索引其实已建成，却读不到。
    # 因此索引核对一律走 sqlite_master 直查。
    # 口径（D7 §4.1）：显式 10 条（sql IS NOT NULL）+ 自动 6 条（sql IS NULL）= 16
    with engine.connect() as conn:
        idx_rows = conn.exec_driver_sql(
            "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index'").fetchall()
    explicit_idx: dict[str, int] = {}
    for name, tbl, sql in idx_rows:
        if sql is not None:
            explicit_idx[tbl] = explicit_idx.get(tbl, 0) + 1
    n_auto_idx = sum(1 for _, _, sql in idx_rows if sql is None)
    n_explicit_idx = sum(explicit_idx.values())

    # ---- 表与字段 ----
    print()
    print(f'  已建表 {len(tabs)} 张（期望 7）')
    if len(tabs) != 7:
        problems.append(f'表数量不符：{len(tabs)}')

    print()
    print(f'  {"表名":<22s} {"字段":>4s} {"期望":>4s} {"显式索引":>8s} {"期望":>4s} {"外键":>4s} {"期望":>4s}')
    print('  ' + '-' * 62)
    tot_f = tot_i = tot_k = 0
    for t in tabs:
        nf = len(insp.get_columns(t))
        ni = explicit_idx.get(t, 0)
        nk = len(insp.get_foreign_keys(t))
        tot_f += nf; tot_i += ni; tot_k += nk
        ef = EXPECT_FIELDS.get(t, -1)
        ei = EXPECT_EXPLICIT_IDX.get(t, -1)
        ek = EXPECT_FK.get(t, -1)
        mf = '✓' if nf == ef else '✗'
        mi = '✓' if ni == ei else '✗'
        mk = '✓' if nk == ek else '✗'
        if nf != ef:
            problems.append(f'{t} 字段 {nf}，期望 {ef}')
        if ni != ei:
            problems.append(f'{t} 显式索引 {ni}，期望 {ei}')
        if nk != ek:
            problems.append(f'{t} 外键 {nk}，期望 {ek}')
        print(f'  {t:<22s} {nf:>4d} {mf}{ef:>3d} {ni:>8d} {mi}{ei:>3d} {nk:>4d} {mk}{ek:>3d}')
    print('  ' + '-' * 62)
    print(f'  {"合计":<22s} {tot_f:>4d} {"64":>4s} {tot_i:>8d} {"10":>4s} {tot_k:>4d} {"6":>4s}')
    if tot_f != 64:
        problems.append(f'字段总数 {tot_f}，期望 64')
    if tot_i != 10:
        problems.append(f'显式索引总数 {tot_i}，期望 10')
    if tot_k != 6:
        problems.append(f'外键总数 {tot_k}，期望 6')

    print()
    print(f'  索引总数 {n_explicit_idx + n_auto_idx} = 显式 {n_explicit_idx} + 自动 {n_auto_idx}  （D7 期望 10 + 6 = 16）')
    if n_explicit_idx + n_auto_idx != 16:
        problems.append(f'索引总数 {n_explicit_idx + n_auto_idx}，期望 16')
    if n_auto_idx != 6:
        problems.append(f'自动索引 {n_auto_idx}，期望 6')

    # ---- 外键删除策略 ----
    print()
    print('  外键删除策略核对（6 个，方向相反，关键差异）')
    seen: dict[tuple[str, str], tuple[str, str]] = {}
    for t in tabs:
        for fk in insp.get_foreign_keys(t):
            seen[(t, fk['constrained_columns'][0])] = (
                fk['referred_table'],
                str(fk.get('options', {}).get('ondelete', '')).upper())
    for key, want in EXPECT_FK_ONDELETE.items():
        got = seen.get(key)
        t, c = key
        if got is None:
            print(f'    ✗ {t}.{c:<20s} 缺外键')
            problems.append(f'{t}.{c} 缺外键')
            continue
        ref, ondel = got
        ok = ondel.replace(' ', '') == want.replace(' ', '')
        if not ok:
            problems.append(f'{t}.{c} ondelete={ondel}，期望 {want}')
        print(f'    {"✓" if ok else "✗"} {t + "." + c:<40s} → {ref:<18s} ON DELETE {ondel}  (期望 {want})')

    # ---- 主键类型核对（本设计的关键：主键类型不统一） ----
    print()
    print('  主键类型核对（有意不统一）')
    expect_pk = {
        'user': ('id', 'INTEGER'), 'image_asset': ('id', 'TEXT'),
        'recognition_record': ('id', 'TEXT'), 'species': ('id', 'INTEGER'),
        'system_config': ('key', 'TEXT'), 'operation_log': ('id', 'INTEGER'),
        'guest_usage': ('session_id', 'TEXT'),
    }
    for t, (pk_name, pk_type) in expect_pk.items():
        cols = insp.get_columns(t)
        pk = [c for c in cols if c.get('primary_key')]
        if not pk:
            problems.append(f'{t} 无主键')
            print(f'    ✗ {t:<22s} 无主键')
            continue
        c = pk[0]
        name_ok = c['name'] == pk_name
        # SQLite 的 TEXT 列在 inspector 里报 TEXT，INTEGER 报 INTEGER
        type_ok = pk_type in str(c['type']).upper()
        ok = name_ok and type_ok
        if not ok:
            problems.append(f'{t} 主键 {c["name"]}/{c["type"]}，期望 {pk_name}/{pk_type}')
        print(f'    {"✓" if ok else "✗"} {t:<22s} PK={c["name"]:<12s} type={str(c["type"]):<10s} (期望 {pk_name}/{pk_type})')

    # ---- 列级 UNIQUE 与函数唯一索引 ----
    print()
    print('  唯一性保障核对')
    for t, c, kind in [
        ('user', 'username', '列级 UNIQUE'),
        ('user', 'LOWER(username)', '函数唯一索引'),
        ('species', 'class_index', '列级 UNIQUE'),
    ]:
        if c.startswith('LOWER'):
            # 同样绕开 inspector 的表达式索引反射缺陷，直查 sqlite_master
            with engine.connect() as conn:
                row = conn.exec_driver_sql(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                    ('idx_user_username_lower',)).fetchone()
            ok = row is not None and 'unique' in (row[0] or '').lower()
        else:
            cols = {cc['name']: cc for cc in insp.get_columns(t)}
            uqs = insp.get_unique_constraints(t)
            ok = bool(cols.get(c, {}).get('unique')) or \
                any(set(u['column_names']) == {c} for u in uqs)
        if not ok:
            problems.append(f'{t}.{c} 缺 {kind}')
        print(f'    {"✓" if ok else "✗"} {t}.{c:<20s} {kind}')

    # ---- 复合索引 ----
    print()
    print('  复合索引核对')
    idx_names = {name for name, _, _ in idx_rows}
    for t, want in [('recognition_record', 'idx_record_user_created'),
                    ('recognition_record', 'idx_record_deleted'),
                    ('operation_log', 'idx_log_user_created'),
                    ('image_asset', 'idx_image_asset_user_created')]:
        ok = want in idx_names
        if not ok:
            problems.append(f'{t} 缺索引 {want}')
        print(f'    {"✓" if ok else "✗"} {t}.{want}')

    # ---- CHECK 约束 ----
    print()
    print('  CHECK 约束核对')
    with engine.connect() as conn:
        for t in tabs:
            rows = conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchall()
            sql = rows[0][0] if rows else ''
            n = sql.upper().count('CHECK')
            print(f'    {t:<22s} CHECK 数 {n}')

    # ---- 汇总 ----
    print()
    if problems:
        print(f'  ✗ 发现 {len(problems)} 个问题：')
        for p in problems:
            print(f'      - {p}')
        return 1
    print('  ✓ 全部核对通过（7 表 / 64 字段 / 10 显式索引 / 6 外键 / 主键类型符合设计）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
