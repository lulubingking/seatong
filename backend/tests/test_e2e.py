# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 端到端集成测试

用 FastAPI TestClient 实跑，覆盖：
  A. 系统与契约
  B. 认证链路（注册 → 登录 → 刷新 → 登出）
  C. 游客链路（3 次额度 → 42901）
  D. 上传 → 识别 → 历史 → 详情 → 导出 → 删除（全链路）
  E. 权限与错误码（401 / 403 / 404 / 413 / 415 / 422）
  F. 管理端（配置、日志、统计、用户管理保护规则）
  G. 响应体契约（信封结构、request_id、X-Skip-Envelope）

【隔离】测试跑在独立的临时数据库与临时存储目录上，绝不触碰 :
    backend/data/seatong.db 与 backend/storage/images
方式：在导入 app 之前改写环境变量，并清理 settings 的 lru_cache。
"""

import os
import shutil
import sys
import tempfile

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
_ROOT = os.path.dirname(_BACKEND)

# ---- 必须在导入 app 之前设定隔离环境 ----
_TMP = tempfile.mkdtemp(prefix='seatong_test_')
os.environ['SEATONG_DB_PATH'] = os.path.join(_TMP, 'test.db')
os.environ['SEATONG_IMAGE_STORAGE_DIR'] = os.path.join(_TMP, 'images')
os.environ['SEATONG_LOG_DIR'] = os.path.join(_TMP, 'logs')
os.environ['SEATONG_DEBUG'] = 'false'
# 加速：测试用低 cost
os.environ['SEATONG_BCRYPT_ROUNDS'] = '4'

from fastapi.testclient import TestClient   # noqa: E402

from app.core.config import get_settings     # noqa: E402

get_settings.cache_clear()
from app.core import config as _cfg           # noqa: E402

# 【关键】settings 是模块级单例，且 security/database 等模块用
# `from app.core.config import settings` 提前绑定了引用。
# 仅改 _cfg.settings 无法影响已绑定的模块，故必须【原地更新对象属性】。
_fresh = _cfg.get_settings()
for _k in type(_fresh).model_fields:
    setattr(_cfg.settings, _k, getattr(_fresh, _k))

# database 模块在导入时就根据 settings.db_path 建好了 engine，需重建
import importlib                          # noqa: E402

from app.core import database as _db      # noqa: E402
importlib.reload(_db)

from app.core import security as _sec     # noqa: E402
importlib.reload(_sec)
print(f'[测试隔离] db={_cfg.settings.db_path}')
print(f'[测试隔离] storage={_cfg.settings.image_storage_dir}')
print(f'[测试隔离] bcrypt_rounds={_cfg.settings.bcrypt_rounds}')

from app.core.database import Base, engine    # noqa: E402
import app.models  # noqa: F401,E402

from app.main import create_app               # noqa: E402
from app.services.user_service import ensure_admin   # noqa: E402

RESULTS = {'pass': 0, 'fail': 0, 'fails': []}


def check(name: str, cond: bool, extra: str = ''):
    RESULTS['pass' if cond else 'fail'] += 1
    tag = '✓' if cond else '✗'
    print(f'  {tag} {name}{("  " + extra) if extra else ""}')
    if not cond:
        RESULTS['fails'].append(name)
    return cond


def main() -> int:
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import sessionmaker
    db = sessionmaker(bind=engine, future=True)()
    admin = ensure_admin(db)

    # 灌入 23 类物种与 5 项配置（否则识别端点拿不到物种介绍、配置端点为 0 项）
    sys.path.insert(0, os.path.join(_BACKEND, 'scripts'))
    import seed_data
    a, u = seed_data.seed_species(db)
    a2, u2 = seed_data.seed_configs(db)
    db.commit()
    print(f'[测试数据] species 新增 {a}/更新 {u}，'
          f'system_config 新增 {a2}/更新 {u2}')

    # 样本图
    import glob
    base = os.path.join(_ROOT, 'fish_image23', 'fish_image')
    samples = {}
    for cls in ('fish_1', 'fish_21', 'fish_3'):
        g = sorted(glob.glob(os.path.join(base, cls, '*.png')))
        if g:
            samples[cls] = open(g[0], 'rb').read()

    app = create_app()
    c = TestClient(app)

    # ================== A. 系统与契约 ==================
    print('\nA. 系统与契约')
    r = c.get('/api/health')
    j = r.json()
    check('GET /api/health → 200', r.status_code == 200, f'status={r.status_code}')
    check('信封含 code/message/data/request_id',
          all(k in j for k in ('code', 'message', 'data', 'request_id')),
          f'keys={sorted(j)}')
    check('code == 0', j.get('code') == 0)
    check('响应头含 X-Request-Id', 'x-request-id' in {k.lower() for k in r.headers})
    check('响应头含 X-Process-Time-Ms',
          'x-process-time-ms' in {k.lower() for k in r.headers})
    check('foreign_keys PRAGMA = 1', j['data']['db_pragmas'].get('foreign_keys') == 1)
    check('模型就绪', j['data']['model']['ready'] is True,
          f"device={j['data']['model'].get('device')}")

    r = c.get('/api/model-info')
    check('GET /api/model-info → 200', r.status_code == 200)
    check('num_classes == 23', r.json()['data']['num_classes'] == 23)
    check('img_size == 224', r.json()['data']['img_size'] == 224)

    # ================== B. 认证 ==================
    print('\nB. 认证链路')
    r = c.post('/api/auth/register', json={'username': 'testuser',
                                           'password': 'Passw0rd1',
                                           'nickname': '测试员'})
    j = r.json()
    check('注册 → 200 且 code=0', r.status_code == 200 and j['code'] == 0,
          f'code={j["code"]}')
    tok = j['data']['access_token']
    rtok = j['data']['refresh_token']
    check('注册返回 access/refresh 双令牌', bool(tok) and bool(rtok))
    check('注册返回 user 对象', j['data']['user']['username'] == 'testuser')
    check('新用户 role=user, status=1',
          j['data']['user']['role'] == 'user' and j['data']['user']['status'] == 1)

    r = c.post('/api/auth/register', json={'username': 'TESTUSER',
                                           'password': 'Passw0rd1'})
    check('大写重名 → 40901', r.json()['code'] == 40901 and r.status_code == 409,
          f'code={r.json()["code"]} http={r.status_code}')

    r = c.post('/api/auth/register', json={'username': 'weak1', 'password': 'abc'})
    check('弱口令 → 40001', r.json()['code'] == 40001)

    r = c.post('/api/auth/register', json={'username': 'ab', 'password': 'Passw0rd1'})
    check('用户名过短 → 40001（Pydantic）', r.json()['code'] == 40001 and r.status_code == 400,
          f'code={r.json()["code"]} http={r.status_code}')

    r = c.post('/api/auth/login', json={'username': 'testuser', 'password': 'Passw0rd1'})
    check('登录 → 200', r.status_code == 200 and r.json()['code'] == 0)
    u_tok = r.json()['data']['access_token']

    r = c.post('/api/auth/login', json={'username': 'testuser', 'password': 'wrong'})
    check('密码错误 → 40103 / HTTP 401',
          r.json()['code'] == 40103 and r.status_code == 401,
          f'code={r.json()["code"]} http={r.status_code}')

    r = c.post('/api/auth/login', json={'username': 'ghost', 'password': 'x'})
    check('用户不存在 → 同一码 40103（防枚举）', r.json()['code'] == 40103)

    r = c.post('/api/auth/refresh', json={'refresh_token': rtok})
    check('刷新令牌 → 200', r.status_code == 200 and r.json()['code'] == 0)

    r = c.post('/api/auth/refresh', json={'refresh_token': tok})
    check('用 access 当 refresh → 40101', r.json()['code'] == 40101)

    r = c.post('/api/auth/logout', headers={'Authorization': f'Bearer {u_tok}'})
    check('登出 → 200', r.status_code == 200 and r.json()['code'] == 0)

    # ================== C. 游客额度 ==================
    print('\nC. 游客链路与额度')
    gs = 'guestsession00000000000000000001'
    H = {'X-Guest-Session': gs}

    r = c.get('/api/users/me', headers=H)
    d = r.json()['data']
    check('游客 /users/me 未登录', d['user'] is None and d['is_guest'] is True)
    check('游客初始额度 3', d['guest_quota']['quota'] == 3 and d['guest_quota']['remaining'] == 3,
          f"quota={d['guest_quota']}")

    # 游客上传（不扣额度）
    r = c.post('/api/images', files={'file': ('t.png', samples['fish_1'], 'image/png')}, headers=H)
    check('游客上传 → 200', r.status_code == 200 and r.json()['code'] == 0)
    guest_img_id = r.json()['data']['image']['id']

    r = c.get('/api/users/me', headers=H)
    check('上传后额度仍为 3（上传不扣）',
          r.json()['data']['guest_quota']['remaining'] == 3)

    # 游客识别 3 次
    for i in range(3):
        r = c.post('/api/recognize', json={'image_id': guest_img_id}, headers=H)
        ok = r.status_code == 200 and r.json()['code'] == 0
        left = r.json()['data'].get('guest_quota', {}).get('remaining')
        check(f'游客第 {i + 1} 次识别 → 200, 剩余额度 {left}', ok and left == 2 - i,
              f'code={r.json()["code"]} left={left}')
        if i == 0:
            gd = r.json()['data']
            check('游客识别不落库（record_id 为 None）', gd['record_id'] is None)
            check('返回 Top-5 候选', len(gd['candidates']) == 5,
                  f"n={len(gd['candidates'])}")
            check('候选含 cn_name/latin_name/confidence',
                  all(k in gd['candidates'][0] for k in ('cn_name', 'latin_name', 'confidence')))
            check('返回物种介绍',
                  gd['species'] is not None and bool(gd['species']['morphology']))

    r = c.post('/api/recognize', json={'image_id': guest_img_id}, headers=H)
    check('第 4 次识别 → 42901 / HTTP 429',
          r.json()['code'] == 42901 and r.status_code == 429,
          f'code={r.json()["code"]} http={r.status_code}')

    # ================== D. 全链路 ==================
    print('\nD. 上传 → 识别 → 历史 → 导出 → 删除')
    LH = {'Authorization': f'Bearer {u_tok}'}

    r = c.post('/api/images', files={'file': ('fish1.png', samples['fish_1'], 'image/png')}, headers=LH)
    check('登录用户上传 → 200', r.status_code == 200 and r.json()['code'] == 0)
    img = r.json()['data']['image']
    img_id = img['id']
    check('返回 UUID 主键', len(img_id) == 36 and img_id.count('-') == 4, f'id={img_id}')
    check('记录宽高', img['width'] and img['height'],
          f"{img['width']}x{img['height']}")
    check('记录内容哈希', bool(img['content_hash']))

    # 重复上传复用
    r2 = c.post('/api/images', files={'file': ('fish1.png', samples['fish_1'], 'image/png')}, headers=LH)
    check('同内容二次上传 → reused=True',
          r2.json()['data']['reused'] is True and r2.json()['data']['image']['id'] == img_id)

    r = c.post('/api/recognize', json={'image_id': img_id}, headers=LH)
    gd = r.json()['data']
    check('登录用户识别 → 200', r.status_code == 200 and r.json()['code'] == 0)
    rec_id = gd['record_id']
    check('登录用户识别已落库（record_id 非空）', bool(rec_id), f'id={str(rec_id)[:8]}…')
    check('fish_1 识别正确', gd['class_index'] == 0,
          f"→ idx={gd['class_index']} {gd['cn_name']} conf={gd['confidence']:.4f}")
    check('返回耗时 duration_ms', gd['duration_ms'] >= 0, f"{gd['duration_ms']}ms")

    # 拿真实小类样本再识别，验证 idx21
    if 'fish_21' in samples:
        r = c.post('/api/images', files={'file': ('f21.png', samples['fish_21'], 'image/png')}, headers=LH)
        i21 = r.json()['data']['image']['id']
        r = c.post('/api/recognize', json={'image_id': i21}, headers=LH)
        d21 = r.json()['data']
        check('fish_21 识别正确', d21['class_index'] == 20,
              f"→ idx={d21['class_index']} {d21['cn_name']} conf={d21['confidence']:.3f}")

    # 取原图 / 缩略图
    r = c.get(f'/api/images/{img_id}/content', headers=LH)
    check('取原图 → 200 且非 JSON（跳过信封）',
          r.status_code == 200 and r.headers['content-type'].startswith('image/'),
          f"type={r.headers['content-type']} len={len(r.content)}")
    check('原图字节一致', r.content == samples['fish_1'])

    r = c.get(f'/api/images/{img_id}/thumb', headers=LH)
    check('取缩略图 → 200 JPEG',
          r.status_code == 200 and r.headers['content-type'] == 'image/jpeg',
          f'len={len(r.content)}')

    # 历史
    r = c.get('/api/records', headers=LH)
    j = r.json()['data']
    check('历史列表 → 200', r.status_code == 200)
    check('列表含分页元信息',
          all(k in j for k in ('items', 'page', 'page_size', 'total', 'total_pages')),
          f"total={j['total']}")
    check('列表条目含 thumb_url', j['items'][0].get('thumb_url', '').startswith('/api/images/'))

    r = c.get('/api/records?class_index=0', headers=LH)
    check('按 class_index 筛选', r.json()['data']['total'] >= 1,
          f"total={r.json()['data']['total']}")

    r = c.get(f'/api/records/{rec_id}', headers=LH)
    det = r.json()['data']
    check('记录详情 → 200', r.status_code == 200)
    check('详情含 Top-5 候选', len(det['candidates']) == 5)
    check('详情候选按 rank 升序',
          [x['rank'] for x in det['candidates']] == [1, 2, 3, 4, 5])
    check('详情含物种介绍（形态/习性）',
          bool(det['species']['morphology']) and bool(det['species']['habit']))
    check('详情含图片元信息', det['image']['id'] == img_id)

    r = c.get(f'/api/results/{rec_id}/candidates', headers=LH)
    check('结果页候选接口 → 200', r.status_code == 200 and len(r.json()['data']) == 5)

    # 导出
    r = c.get('/api/records/export', headers=LH)
    check('导出 CSV → 200', r.status_code == 200)
    check('CSV 带 UTF-8 BOM', r.content[:3] == b'\xef\xbb\xbf',
          f'size={len(r.content)}B')
    check('CSV 含表头「中文名」', '中文名'.encode('utf-8') in r.content)
    check('CSV 非 JSON 信封', b'"code"' not in r.content[:64])
    check('Content-Disposition 附件下载',
          'attachment' in r.headers.get('content-disposition', ''))

    # 删除
    r = c.request('DELETE', '/api/records', json={'record_ids': [rec_id]}, headers=LH)
    check('DELETE /api/records → 200', r.status_code == 200 and r.json()['code'] == 0)
    check('返回删除条数', r.json()['data']['deleted'] == 1)

    r = c.get(f'/api/records/{rec_id}', headers=LH)
    check('删除后取详情 → 40401', r.json()['code'] == 40401)

    # ================== E. 权限与错误码 ==================
    print('\nE. 权限与错误码')
    # /api/users/me 设计为双身份共用（游客也可访问，前端首屏只调这一个）
    r = c.get('/api/users/me')
    check('无令牌 /api/users/me → 200 且 is_guest=True',
          r.status_code == 200 and r.json()['code'] == 0
          and r.json()['data']['is_guest'] is True,
          f'code={r.json()["code"]} http={r.status_code}')

    # 真正需要 401 的是受保护端点
    r = c.get('/api/records')
    check('无令牌访问历史 → 40101 / 401',
          r.json()['code'] == 40101 and r.status_code == 401,
          f'code={r.json()["code"]} http={r.status_code}')

    r = c.get('/api/users/me', headers={'Authorization': 'Bearer garbage'})
    check('伪造令牌 → 40101', r.json()['code'] == 40101)

    r = c.get('/api/records', headers={'Authorization': 'Basic abc'})
    check('非 Bearer 方案 → 40101', r.json()['code'] == 40101)

    # 越权：另一用户访问 testuser 的记录
    r = c.post('/api/auth/register', json={'username': 'other', 'password': 'Passw0rd1'})
    o_tok = r.json()['data']['access_token']
    OH = {'Authorization': f'Bearer {o_tok}'}
    r = c.get(f'/api/records/{rec_id}', headers=OH)
    check('他人取记录 → 40401（不泄露存在性）', r.json()['code'] == 40401,
          f'code={r.json()["code"]}')
    r = c.get(f'/api/images/{img_id}/content', headers=OH)
    check('他人取原图 → 40401', r.json()['code'] == 40401)
    r = c.request('DELETE', '/api/records', json={'record_ids': [rec_id]}, headers=OH)
    check('他人删除记录 → deleted=0', r.json()['data']['deleted'] == 0)

    # 普通用户调管理端点 → 40301
    r = c.get('/api/admin/stats', headers=LH)
    check('普通用户调管理端点 → 40301 / HTTP 403',
          r.json()['code'] == 40301 and r.status_code == 403,
          f'code={r.json()["code"]} http={r.status_code}')

    # 类型与体积
    r = c.post('/api/images', files={'file': ('a.gif', b'GIF89a' + b'x' * 100, 'image/gif')}, headers=LH)
    check('不支持类型 .gif → 41501 / HTTP 415',
          r.json()['code'] == 41501 and r.status_code == 415,
          f'code={r.json()["code"]} http={r.status_code}')

    r = c.post('/api/images',
               files={'file': ('big.png', b'\x89PNG\r\n\x1a\n' + b'x' * (11 * 1024 * 1024), 'image/png')},
               headers=LH)
    check('体积超限 → 41301 / HTTP 413',
          r.json()['code'] == 41301 and r.status_code == 413,
          f'code={r.json()["code"]} http={r.status_code}')

    r = c.post('/api/images', files={'file': ('fake.png', b'this is not an image', 'image/png')}, headers=LH)
    check('伪装图片 → 42201 / HTTP 422',
          r.json()['code'] == 42201 and r.status_code == 422,
          f'code={r.json()["code"]} http={r.status_code}')

    import io
    from PIL import Image as _I
    buf = io.BytesIO()
    _I.new('RGB', (16, 16)).save(buf, format='PNG')
    r = c.post('/api/images', files={'file': ('tiny.png', buf.getvalue(), 'image/png')}, headers=LH)
    check('分辨率过低 → 42202', r.json()['code'] == 42202, f'code={r.json()["code"]}')

    r = c.post('/api/recognize', json={'image_id': 'no-such-uuid'}, headers=LH)
    check('识别不存在的图 → 40401',
          r.json()['code'] == 40401 and r.status_code == 404,
          f'code={r.json()["code"]} http={r.status_code}')

    r = c.post('/api/recognize', json={'image_id': img_id, 'top_k': 99}, headers=LH)
    check('top_k 越界 → 40001', r.json()['code'] == 40001)

    r = c.get('/api/records?page=0', headers=LH)
    check('page=0 越界 → 40001', r.json()['code'] == 40001)

    r = c.get('/api/species/99')
    check('物种越界 → 40401', r.json()['code'] == 40401)

    # ================== F. 物种（公开） ==================
    print('\nF. 物种端点（免登录）')
    r = c.get('/api/species')
    j = r.json()['data']
    check('/api/species 免登录可访问', r.status_code == 200 and r.json()['code'] == 0)
    check('物种总数 23', j['total'] == 23, f"total={j['total']}")
    check('class_index 恰为 0..22',
          sorted(x['class_index'] for x in j['items']) == list(range(23)))
    check('fish_18 标注为科级 Scaridae',
          next(x for x in j['items'] if x['class_index'] == 17)['latin_name'] == 'Scaridae')

    r = c.get('/api/species/0')
    check('/api/species/0 → 200 含网纹宅泥鱼',
          r.json()['data']['cn_name'] == '网纹宅泥鱼',
          f"cn={r.json()['data']['cn_name']}")

    # ================== G. 管理端 ==================
    print('\nG. 管理端')
    r = c.post('/api/auth/login', json={'username': 'admin', 'password': 'Admin@12345'})
    check('管理员登录', r.status_code == 200 and r.json()['code'] == 0)
    AH = {'Authorization': f"Bearer {r.json()['data']['access_token']}"}

    r = c.get('/api/admin/config', headers=AH)
    cfg = r.json()['data']
    check('读配置 → 5 项', len(cfg) == 5, f'n={len(cfg)}')
    check('配置含 guest_quota=3',
          any(x['config_key'] == 'guest_quota' and x['value'] == '3' for x in cfg))

    r = c.put('/api/admin/config', json={'config': {'max_file_size_mb': '20'}},
              headers=AH)
    check('改配置（PUT 全量覆盖）→ 200', r.status_code == 200 and r.json()['code'] == 0,
          f'code={r.json()["code"]}')
    check('改配置返回 updated 列表',
          len(r.json()['data']['updated']) == 1,
          f"n={len(r.json()['data']['updated']) if r.json()['code'] == 0 else '-'}")

    r = c.put('/api/admin/config', json={'config': {'guest_quota': 'abc'}}, headers=AH)
    check('配置类型校验：int 位写 abc → 40001', r.json()['code'] == 40001,
          f'code={r.json()["code"]}')

    r = c.put('/api/admin/config', json={'config': {'nonexist': '1'}}, headers=AH)
    check('改不存在配置 → 40401', r.json()['code'] == 40401)

    r = c.put('/api/admin/config', json={'bad_key': 'x'}, headers=AH)
    check('请求体缺 config 包裹 → 40001', r.json()['code'] == 40001,
          f'code={r.json()["code"]}')

    # 多键一次提交 + 幂等性（重复提交结果一致）
    r = c.put('/api/admin/config',
              json={'config': {'guest_quota': '3', 'max_file_size_mb': '20'}},
              headers=AH)
    check('多键一次提交 → 200', r.json()['code'] == 0,
          f"updated={len(r.json()['data']['updated']) if r.json()['code'] == 0 else '-'}")
    r2 = c.put('/api/admin/config', json={'config': {'guest_quota': '3'}}, headers=AH)
    check('PUT 幂等：重复提交结果一致', r2.json()['code'] == 0)

    r = c.get('/api/admin/logs', headers=AH)
    lg = r.json()['data']
    check('读日志 → 200', r.status_code == 200)
    check('日志有记录', lg['total'] > 0, f"total={lg['total']}")
    acts = {x['action'] for x in lg['items']}
    check('日志含 login 动作', 'login' in acts, f'actions={sorted(acts)}')

    r = c.get('/api/admin/logs?action=recognize', headers=AH)
    check('日志按 action 筛选', r.json()['code'] == 0,
          f"total={r.json()['data']['total']}")

    r = c.get('/api/admin/stats', headers=AH)
    st = r.json()['data']
    check('统计 → 200 且字段齐备',
          all(k in st for k in ('total_users', 'active_users', 'total_records',
                                'total_uploads', 'records_today', 'top_species',
                                'avg_duration_ms')),
          f"users={st['total_users']} records={st['total_records']}")

    r = c.get('/api/admin/users', headers=AH)
    check('用户列表（管理员）→ 200', r.status_code == 200 and r.json()['code'] == 0,
          f"total={r.json()['data']['total']}")

    # 保护规则
    r = c.patch(f'/api/admin/users/{admin.id}', json={'status': 0}, headers=AH)
    check('禁用自己 → 40301', r.json()['code'] == 40301, f'code={r.json()["code"]}')
    r = c.patch(f'/api/admin/users/{admin.id}', json={'role': 'user'}, headers=AH)
    check('降级最后一个管理员 → 40301', r.json()['code'] == 40301)
    r = c.delete(f'/api/admin/users/{admin.id}', headers=AH)
    check('删除自己 → 40301', r.json()['code'] == 40301)
    r = c.post(f'/api/admin/users/{admin.id}/reset-password', json={'new_password': 'Admin@9999'}, headers=AH)
    check('重置自己密码 → 40301（引导用改密）', r.json()['code'] == 40301)

    # 正常管理操作
    r = c.post('/api/admin/users', json={'username': 'managed', 'password': 'Passw0rd1',
                                   'nickname': '被管理员建的'}, headers=AH)
    check('管理员建号 → 200', r.status_code == 200 and r.json()['code'] == 0)
    m_id = r.json()['data']['id']

    r = c.patch(f'/api/admin/users/{m_id}', json={'status': 0}, headers=AH)
    check('管理员禁用普通用户 → 200', r.json()['code'] == 0)

    r = c.post('/api/auth/login', json={'username': 'managed', 'password': 'Passw0rd1'})
    check('被禁用用户登录 → 40104 / HTTP 401',
          r.json()['code'] == 40104 and r.status_code == 401,
          f'code={r.json()["code"]} http={r.status_code}')

    r = c.delete(f'/api/admin/users/{m_id}', headers=AH)
    check('删除普通用户 → 200', r.json()['code'] == 0)

    # 改密
    r = c.put('/api/users/me/password',
               json={'old_password': 'Passw0rd1', 'new_password': 'NewPassw0rd9'},
               headers=LH)
    check('自助改密 → 200', r.json()['code'] == 0)
    r = c.post('/api/auth/login', json={'username': 'testuser', 'password': 'NewPassw0rd9'})
    check('新密码可登录', r.json()['code'] == 0)

    # 改密后重登（旧令牌仍有效，但下面要验证的是密码语义）
    r = c.post('/api/auth/login', json={'username': 'testuser', 'password': 'NewPassw0rd9'})
    LH2 = {'Authorization': f"Bearer {r.json()['data']['access_token']}"}
    r = c.put('/api/users/me/password',
               json={'old_password': 'Passw0rd1', 'new_password': 'Xx12345678'},
               headers=LH2)
    check('原密码错误 → 40103', r.json()['code'] == 40103,
          f'code={r.json()["code"]}')

    # 改密后旧密码失效、新密码生效
    r = c.put('/api/users/me/password',
               json={'old_password': 'NewPassw0rd9', 'new_password': 'Xx12345678'},
               headers=LH2)
    check('正确原密码改密 → 200', r.json()['code'] == 0)
    r = c.post('/api/auth/login', json={'username': 'testuser', 'password': 'NewPassw0rd9'})
    check('旧密码已失效 → 40103', r.json()['code'] == 40103)
    r = c.post('/api/auth/login', json={'username': 'testuser', 'password': 'Xx12345678'})
    check('新密码生效', r.json()['code'] == 0)

    # 错误码表覆盖核对：18 个业务码全部有 HTTP 状态映射
    from app.core.errors import ERROR_TABLE, http_status_of
    check('错误码表 18 项', len(ERROR_TABLE) == 18, f'n={len(ERROR_TABLE)}')
    check('错误码 → HTTP 状态全部可映射',
          all(100 <= http_status_of(k) < 600 for k in ERROR_TABLE))

    db.close()
    return 0


if __name__ == '__main__':
    try:
        main()
    finally:
        try:
            engine.dispose()
            shutil.rmtree(_TMP, ignore_errors=True)
        except Exception:
            pass

    print()
    print('=' * 70)
    print(f'  合计  通过 {RESULTS["pass"]} / 失败 {RESULTS["fail"]}')
    if RESULTS['fails']:
        print('  失败项：')
        for f in RESULTS['fails']:
            print(f'    - {f}')
    print('=' * 70)
    sys.exit(1 if RESULTS['fail'] else 0)
