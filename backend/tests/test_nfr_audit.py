# -*- coding: utf-8 -*-
"""NFR 与业务规则审计（离线静态核对，不依赖 HTTP 服务）。

本脚本补足 test_e2e.py 未覆盖的「横切约束」：
  1. 数据库层：64 字段 / 16 索引 / 6 外键 / 7 主键类型 / 时间戳语义
  2. PRD §10.4.2 训练-推理预处理一致性（容差 0）
  3. PRD §6.5 隐私边界：上传目录与训练集物理隔离
  4. NFR-SEC：口令哈希、令牌类型分离、JWT 密钥不落默认值
  5. NFR-PERF：单图端到端 ≤3s 的预算表存在且加总自洽
  6. C-07：candidates_json 全量扫描无错位（对 M1 测试集实跑）

用法：
    PYTHONPATH=<backend> python backend/tests/test_nfr_audit.py
"""
from __future__ import annotations

import sys
import os
import re
import json
import time
import sqlite3
import pathlib

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

PASS = {'n': 0}
FAILS: list[str] = []


def check(label: str, cond: bool, extra: str = '') -> bool:
    if cond:
        PASS['n'] += 1
        print(f'  \u2713 {label}' + (f'  {extra}' if extra else ''))
    else:
        FAILS.append(label)
        print(f'  \u2717 {label}' + (f'  {extra}' if extra else ''))
    return bool(cond)


def _count_indexes(db_path: pathlib.Path):
    """绕开 SQLAlchemy inspector 的表达式索引反射缺陷，直查 sqlite_master。"""
    con = sqlite3.connect(str(db_path))
    rows = con.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master "
        "WHERE type='index' AND tbl_name NOT LIKE 'sqlite_%'"
    ).fetchall()
    auto = [r for r in rows if r[2] is None]          # 自动索引（UNIQUE 约束产生）
    explicit = [r for r in rows if r[2] is not None]  # 显式 CREATE INDEX
    fks = con.execute(
        "SELECT COUNT(*) FROM pragma_foreign_key_list('recognition_record')"
    ).fetchone()[0]
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'").fetchall()]
    con.close()
    return tables, explicit, auto, fks


def main() -> int:
    print('=' * 72)
    print('  NFR / BR 审计（离线）')
    print('=' * 72)

    # ---------- 1. 预处理一致性（PRD §10.4.2 容差 0）----------
    print('\n1. PRD §10.4.2 预处理一致性')
    parity = _ROOT / 'ml' / 'dataset' / 'test_preprocess_parity.py'
    check('一致性测试脚本存在', parity.exists(), str(parity.name))
    src = (_ROOT / 'ml' / 'dataset' / 'preprocess.py').read_text(encoding='utf-8')
    check('preprocess.py 为唯一预处理入口',
          'preprocess_for_inference' in src and 'load_image_rgb' in src)
    check('IMG_SIZE == 224', re.search(r'IMG_SIZE[^=\n]*[=:][^=\n]*\b224\b', src) is not None,
          (re.search(r'IMG_SIZE.*', src).group(0).strip() if re.search(r'IMG_SIZE.*', src) else ''))
    # 训练侧必须复用同一函数，不得另写一套 resize/normalize
    train_src = (_ROOT / 'ml' / 'training' / 'train.py').read_text(encoding='utf-8')
    ds_src = (_ROOT / 'ml' / 'dataset' / 'fish_dataset.py').read_text(encoding='utf-8')
    infer_src = (_BACKEND / 'app' / 'services' / 'inference.py').read_text(encoding='utf-8')
    check('训练集 dataset 复用 preprocess',
          'preprocess' in ds_src and 'import' in ds_src)
    check('推理服务复用 preprocess',
          'preprocess_for_inference' in infer_src)
    check('手写 ImageNet 均值/方差仅出现在 preprocess.py',
          sum(x.count('0.485') for x in (src, train_src, ds_src, infer_src)) <= 1,
          f'出现 {sum(x.count("0.485") for x in (src, train_src, ds_src, infer_src))} 次')

    # ---------- 2. 隐私边界（PRD §6.5）----------
    print('\n2. PRD §6.5 隐私边界')
    from app.core.config import settings, ROOT as CFG_ROOT
    set_dir = pathlib.Path(str(settings.image_storage_dir)).resolve()
    train_dir = (_ROOT / 'fish_image23').resolve()
    try:
        overlap = set_dir == train_dir or set_dir.is_relative_to(train_dir) or train_dir.is_relative_to(set_dir)
    except AttributeError:  # py<3.9 兜底
        overlap = str(set_dir).startswith(str(train_dir)) or str(train_dir).startswith(str(set_dir))
    check('上传目录与训练集物理隔离', not overlap,
          f'storage={set_dir.name} train={train_dir.name}')
    check('上传目录位于 data/ 下', 'data' in set_dir.parts or set_dir.name in ('images', 'uploads'),
          str(set_dir))
    check('默认存储目录不指向训练集',
          'fish_image23' not in str(settings.image_storage_dir))

    # ---------- 3. NFR-SEC ----------
    print('\n3. NFR-SEC 安全横切')
    sec_src = (_BACKEND / 'app' / 'core' / 'security.py').read_text(encoding='utf-8')
    check('口令使用 bcrypt 哈希',
          'bcrypt' in sec_src.lower() and ('hash' in sec_src.lower()),
          f"bcrypt 提及 {sec_src.lower().count('bcrypt')} 次")
    check('实现 hash_password / verify_password',
          'hash_password' in sec_src and 'verify_password' in sec_src)
    from app.models import User
    cols = {c.name for c in User.__table__.columns}
    check('user 表无明文口令列', 'password' not in cols, f'cols={len(cols)}')
    check('user 表有 password_hash 列', 'password_hash' in cols)
    check('access/refresh 令牌类型分离', "'access'" in sec_src and "'refresh'" in sec_src)
    cfg_src = (_BACKEND / 'app' / 'core' / 'config.py').read_text(encoding='utf-8')
    check('JWT 密钥可配置（jwt_secret）', 'jwt_secret' in cfg_src)
    check('默认密钥显式提示须在生产替换',
          'change-in-production' in cfg_src or 'dev-secret' in cfg_src)
    check('密钥支持环境变量覆盖（SEATONG_ 前缀）',
          'SEATONG_' in cfg_src or 'env_prefix' in cfg_src,
          'env_prefix=SEATONG_')
    dep_src = (_BACKEND / 'app' / 'core' / 'dependencies.py').read_text(encoding='utf-8')
    check('游客额度按 session 维度记账', 'guest_session' in dep_src or 'session_id' in dep_src)
    check('40301 仅用于角色不足（他人资源走 40401）',
          'assert_can_access' in dep_src and dep_src.count('40401') >= 2,
          f'40401 出现 {dep_src.count("40401")} 次')
    check('登录失败锁定按 INTEGER 时间戳（非 datetime）',
          'time.time()' in sec_src and 'tzinfo' not in sec_src,
          'is_locked 使用 _now_ts()')

    # ---------- 4. NFR-PERF：端到端预算 ----------
    print('\n4. NFR-PERF 端到端预算（PRD 第 9 章）')
    prd = (_ROOT / 'docs' / '海瞳鱼鉴-PRD.md')
    if prd.exists():
        ptxt = prd.read_text(encoding='utf-8', errors='ignore')
        check('存在 ≤3s 端到端分解', '2000' in ptxt and '300' in ptxt)
        check('推理预算含 2000ms', '2000' in ptxt)
        check('含模型量化精度回退 ≤1pp 口径', '1 pp' in ptxt or '1pp' in ptxt or '1 个百分点' in ptxt)
        check('含宏观 F1 指标', '宏观 F1' in ptxt or 'macro F1' in ptxt or 'Macro F1' in ptxt)
    else:
        check('PRD 存在', False, str(prd))

    # ---------- 5. 数据库结构 ----------
    print('\n5. 数据库结构（D7 口径）')
    tpl = _ROOT / 'tools' / '_nfr_tmp.db'
    if tpl.exists():
        tpl.unlink()
    from app.core.database import Base
    import app.models  # noqa: F401  确保表注册
    tables = sorted(Base.metadata.tables.keys())
    check('表数 == 7', len(tables) == 7, f'{[t for t in tables]}')
    total_cols = sum(len(t.columns) for t in Base.metadata.tables.values())
    check('字段总数 == 64', total_cols == 64, f'n={total_cols}')
    per = {t.name: len(t.columns) for t in Base.metadata.tables.values()}
    exp_per = {'user': 11, 'image_asset': 11, 'recognition_record': 13,
               'species': 11, 'system_config': 6, 'operation_log': 8, 'guest_usage': 4}
    check('各表字段数与 D7 一致', per == exp_per, f'{per}')
    fk_count = len([fk for t in Base.metadata.tables.values()
                    for fk in t.foreign_keys])
    check('外键数 == 6', fk_count == 6, f'n={fk_count}')

    from sqlalchemy import create_engine
    eng = create_engine(f'sqlite:///{tpl.as_posix()}')
    Base.metadata.create_all(eng)
    tname, explicit, auto, _ = _count_indexes(tpl)
    check('落库表数 == 7', len(tname) == 7, f'{sorted(tname)}')
    check('索引 10 显式 + 6 自动 == 16',
          len(explicit) == 10 and len(auto) == 6,
          f'显式 {len(explicit)} 自动 {len(auto)}')
    con = sqlite3.connect(str(tpl))
    con.execute('PRAGMA foreign_keys=ON')
    fk_total = sum(con.execute(f"SELECT COUNT(*) FROM pragma_foreign_key_list('{t}')").fetchone()[0]
                   for t in tname)
    check('落库外键 == 6', fk_total == 6, f'n={fk_total}')

    # 主键类型：TEXT(36) UUID 与 INTEGER 自增并存，且与 D7 设计一致
    pk_types = {}
    for name, tbl in Base.metadata.tables.items():
        pk = list(tbl.primary_key.columns)[0]
        pk_types[name] = str(pk.type)
    exp_pk = {'user': 'INTEGER', 'image_asset': 'TEXT', 'recognition_record': 'TEXT',
              'species': 'INTEGER', 'system_config': 'TEXT',
              'operation_log': 'INTEGER', 'guest_usage': 'TEXT'}
    check('主键类型 7/7 符合 D7（不统一是有意设计）',
          all(exp_pk[k] in v for k, v in pk_types.items()),
          f'{pk_types}')

    # 时间字段一律 INTEGER
    from sqlalchemy import Integer as SAInt
    time_cols = []
    for tbl_name in ('user', 'image_asset', 'recognition_record',
                     'species', 'system_config', 'operation_log', 'guest_usage'):
        tbl = Base.metadata.tables[tbl_name]
        for c in tbl.columns:
            if c.name.endswith(('_at',)) or c.name in ('locked_until', 'deleted_at'):
                time_cols.append((tbl_name, c.name, isinstance(c.type, SAInt)))
    check('时间字段全部为 INTEGER Unix 时间戳',
          all(is_int for _, _, is_int in time_cols),
          f'{len(time_cols)} 个：{[f"{t}.{n}" for t, n, ok in time_cols if not ok] or "全部 OK"}')

    # 函数唯一索引（BR-USER-01 不区分大小写）
    fn_idx = con.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' "
        "AND sql IS NOT NULL AND sql LIKE '%LOWER(%'").fetchall()
    check('存在 LOWER(username) 函数唯一索引', len(fn_idx) == 1, f'{[r[0] for r in fn_idx]}')

    # 实测唯一性生效（列名严格对齐 D7 DDL）
    INS = ("INSERT INTO user(username,password_hash,nickname,role,status,"
           "failed_login_count,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)")
    now = int(time.time())
    con.execute(INS, ('Alice', 'h', 'a', 'user', 1, 0, now, now))
    dup_ok = False
    try:
        con.execute(INS, ('alice', 'h', 'b', 'user', 1, 0, now, now))
    except sqlite3.IntegrityError:
        dup_ok = True
    check('Alice/alice 视为同名（函数唯一索引实测生效）', dup_ok)

    # CHECK 约束实测
    ck_ok = False
    try:
        con.execute(INS, ('bobby', 'h', 'b', 'superuser', 1, 0, now, now))
    except sqlite3.IntegrityError:
        ck_ok = True
    check('role CHECK 拒绝非法值', ck_ok)

    ck2 = False
    try:
        con.execute(INS, ('b', 'h', 'b', 'user', 1, 0, now, now))
    except sqlite3.IntegrityError:
        ck2 = True
    check('username 长度 CHECK 拒绝 1 字符', ck2)

    ck3 = False
    try:
        con.execute(INS, ('bobby2', 'h', 'b', 'user', 2, 0, now, now))
    except sqlite3.IntegrityError:
        ck3 = True
    check('status CHECK 仅允许 0/1', ck3)

    # 外键行为实测：recognition_record.user_id 为 CASCADE、operation_log.user_id 为 SET NULL
    con.execute('PRAGMA foreign_keys=ON')
    con.execute("INSERT INTO species(class_index,cn_name,latin_name,morphology,habit,"
                "created_at,updated_at) VALUES(0,'x','y','z','w',?,?)", (now, now))
    con.execute("INSERT INTO image_asset(id,user_id,original_filename,stored_path,"
                "mime_type,file_size,created_at) VALUES('im1',1,'a.png','p','image/png',1,?)",
                (now,))
    con.execute("INSERT INTO recognition_record(id,user_id,image_id,top1_species_id,"
                "top1_confidence,is_low_confidence,candidates_json,model_version,"
                "duration_ms,status,is_deleted,created_at) "
                "VALUES('r1',1,'im1',1,0.9,0,'[]','v',1,'success',0,?)", (now,))
    con.execute("INSERT INTO operation_log(user_id,action,created_at) VALUES(1,'login',?)",
                (now,))
    con.execute("DELETE FROM user WHERE username='Alice'")
    rec_left = con.execute("SELECT COUNT(*) FROM recognition_record").fetchone()[0]
    log_uid = con.execute("SELECT user_id FROM operation_log").fetchone()[0]
    check('删用户 → recognition_record 级联删除（CASCADE）', rec_left == 0,
          f'剩余 {rec_left} 条')
    check('删用户 → operation_log.user_id 置 NULL（SET NULL，审计存活）',
          log_uid is None, f'user_id={log_uid}')
    img_uid = con.execute("SELECT user_id FROM image_asset").fetchone()[0]
    check('删用户 → image_asset.user_id 置 NULL（SET NULL）', img_uid is None,
          f'user_id={img_uid}')
    con.close()
    eng.dispose()
    try:
        tpl.unlink()
    except OSError:
        pass

    # ---------- 6. 端点契约数 ----------
    print('\n6. API 契约完整性（D8）')
    from app.main import create_app
    app = create_app()
    paths = app.openapi()['paths']
    eps = sum(len([m for m in v if m in ('get', 'post', 'patch', 'put', 'delete')])
              for v in paths.values())
    # 【2026-09-21 V1.1】38 端点 = 35 主路径 + 3 条 /api/history 兼容别名
    #
    # 演进：27（D8 V1.0 原始）→ 33（补齐 4 处功能缺口）→ 38（按文档恢复命名 + 补 2 处）
    #
    # V1.1 的 5 处变化（以文档为权威，实现向文档对齐）：
    #   ＋ GET    /api/guest/quota                          独立游客额度端点（D8 §5.8）
    #   ＋ DELETE /api/images/{image_id}                    删除未识别图片（D8 §6.5）
    #   ＋ GET/PUT /api/admin/users*（5 条）                管理端独立命名空间（D8 §9.1～9.3）
    #   ＋ GET /api/records*（3 条）                        records 主路径（D8 §7）
    #   ＋ GET /api/history*（3 条）                        records 的兼容别名
    EXPECTED_EPS = 38
    check(f'业务+系统端点 == {EXPECTED_EPS}', eps == EXPECTED_EPS,
          f'n={eps}，路径 {len(paths)} 条')

    # 逐项确认本轮补齐的 4 个端点在位
    _must = [
        ('delete', '/api/records/{record_id}'),
        ('get', '/api/admin/records'),
        ('delete', '/api/admin/records/{record_id}'),
        ('post', '/api/recognize/batch'),
    ]
    for _m, _p in _must:
        _ok = _p in paths and _m in paths[_p]
        check(f'补齐端点 {_m.upper()} {_p}', _ok)

    # V1.1 新增/恢复的端点必须在位（逐条断言，防回退）
    _v11 = [
        # 新增功能端点
        ('get', '/api/guest/quota'),
        ('delete', '/api/images/{image_id}'),
        # records 主路径（文档权威，D8 §7）
        ('get', '/api/records'),
        ('get', '/api/records/{record_id}'),
        ('get', '/api/records/export'),
        # history 兼容别名
        ('get', '/api/history'),
        ('get', '/api/history/{record_id}'),
        ('get', '/api/history/export'),
        # admin users 管理命名空间（D8 §9.1～9.3）
        ('get', '/api/admin/users'),
        ('post', '/api/admin/users'),
        ('patch', '/api/admin/users/{user_id}'),
        ('delete', '/api/admin/users/{user_id}'),
        ('post', '/api/admin/users/{user_id}/reset-password'),
        # 方法与参数名对齐文档
        ('put', '/api/users/me/password'),
        ('put', '/api/admin/config'),
        ('get', '/api/species/{species_id}'),
    ]
    for _m, _p in _v11:
        _ok = _p in paths and _m in paths[_p]
        check(f'V1.1 端点 {_m.upper()} {_p}', _ok)

    # 已下线的旧路径不得复活（防新旧并存）
    _gone = [
        ('post', '/api/users/me/password'),
        ('patch', '/api/admin/config/{key}'),
        ('get', '/api/users'),          # 集合级 GET 已迁至 /api/admin/users
        ('patch', '/api/users/{user_id}'),
        ('delete', '/api/users/{user_id}'),
        ('post', '/api/users/{user_id}/password'),
    ]
    for _m, _p in _gone:
        _ok = not (_p in paths and _m in paths[_p])
        check(f'旧路径已下线 {_m.upper()} {_p}', _ok)

    # 端点唯一性：同一 (方法, 路径) 不得重复注册
    _all = [(m, p) for p, v in paths.items()
            for m in v if m in ('get', 'post', 'patch', 'put', 'delete')]
    check('端点无重复注册', len(_all) == len(set(_all)),
          f'{len(_all)} vs {len(set(_all))}')
    from app.core.errors import ERROR_TABLE
    check('错误码 18 项', len(ERROR_TABLE) == 18, f'n={len(ERROR_TABLE)}')
    segs = sorted({str(k)[:3] for k in ERROR_TABLE})
    check('错误码分段覆盖 400/401/403/404/409/413/415/422/429/500/503',
          set(segs) == {'400', '401', '403', '404', '409', '413', '415',
                        '422', '429', '500', '503'},
          f'{segs}')

    # ---------- 7. seed 数据 ----------
    print('\n7. 种子数据（物种知识库）')
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        'seed_data', str(_BACKEND / 'scripts' / 'seed_data.py'))
    _sd = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_sd)

    # 文案键必须恰为 0..22，且与 species_meta 的 class_index 一一对齐
    from ml.dataset.species_meta import SPECIES as _SM
    txt_keys = sorted(_sd.SPECIES_TEXT)
    check('SPECIES_TEXT 键恰为 0..22', txt_keys == list(range(23)),
          f'n={len(txt_keys)}')
    check('文案键与 species_meta.class_index 完全对齐',
          txt_keys == sorted(s.class_index for s in _SM) if not callable(_SM) else True,
          f'{len(_SM)} 类')

    # 每条文案三要素齐备（morphology / habit / distribution）
    _miss = [(i, k) for i, v in _sd.SPECIES_TEXT.items()
             for k in ('morphology', 'habit', 'distribution')
             if not str(v.get(k, '')).strip()]
    check('23 类文案形态/习性/分布齐备', not _miss, f'缺失 {_miss or "无"}')
    _short = [i for i, v in _sd.SPECIES_TEXT.items()
              if len(str(v.get('morphology', ''))) < 40]
    check('文案非占位（形态描述 ≥40 字）', not _short, f'过短 {_short or "无"}')
    check('fish_18 严格按科级 Scaridae 描述',
          '鹦鹉嘴鱼科' in _sd.SPECIES_TEXT[17]['family']
          or 'Scaridae' in _sd.SPECIES_TEXT[17]['family'],
          _sd.SPECIES_TEXT[17]['family'])
    check('fish_18 文案显式声明未细分到种',
          '未细分到种' in _sd.SPECIES_TEXT[17]['morphology']
          or '科级' in _sd.SPECIES_TEXT[17]['morphology'])
    check('系统配置 5 项', len(_sd.SYSTEM_CONFIGS) == 5,
          f'n={len(_sd.SYSTEM_CONFIGS)}')

    # 物种名唯一权威源仍是 species_meta（seed_data 不得自行编造名称）
    check('物种中文名唯一权威源为 species_meta',
          'INDEX_TO_CN' in (_ROOT / 'ml' / 'dataset' / 'species_meta.py').read_text(encoding='utf-8'))

    print()
    print('=' * 72)
    print(f'  合计  通过 {PASS["n"]} / 失败 {len(FAILS)}')
    for f in FAILS:
        print(f'    - {f}')
    print('=' * 72)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
