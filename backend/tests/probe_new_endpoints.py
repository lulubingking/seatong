# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 新增端点真实服务联调探针

针对 2026-09-21 补齐的 4 处功能缺口，在【真实 HTTP + 真实库 + CUDA】下验证：
  1. DELETE /api/records/{record_id}        单条软删除
  2. GET    /api/admin/records              跨用户记录列表
  3. DELETE /api/admin/records/{record_id}  删任意用户记录
  4. POST   /api/recognize/batch            批量识别

用法（须先启动后端）：
    python tests/probe_new_endpoints.py [base_url]

【隔离提醒】本探针写入真实库 backend/data/seatong.db，
会创建带时间戳前缀的临时账号，并在结束时清理其数据。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
_ROOT = os.path.dirname(_BACKEND)

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
STAMP = time.strftime('%H%M%S')

PASS = 0
FAIL = 0
FAILS = []

# 限流节流（42902：每分钟 60 次）。探针会发较多请求，
# 若不加节流会把自己限住，把 42902 误判为功能缺陷。
_RATE_MIN_INTERVAL = 1.05
_last_call = [0.0]


def check(name, cond, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  \u2713 {name}{("  " + extra) if extra else ""}')
    else:
        FAIL += 1
        FAILS.append(name)
        print(f'  \u2717 {name}{("  " + extra) if extra else ""}')
    return cond


def _throttle():
    """保证任意两次请求间隔 ≥ _RATE_MIN_INTERVAL 秒。"""
    now = time.time()
    wait = _RATE_MIN_INTERVAL - (now - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()


def req(method, path, body=None, headers=None, raw=False, files=None):
    """发一个请求。raw=True 时返回 (status, bytes)。"""
    _throttle()
    url = BASE + path
    hdr = dict(headers or {})
    data = None
    if files is not None:
        boundary = '----probe' + uuid.uuid4().hex
        fname, content, ctype = files
        buf = []
        buf.append(f'--{boundary}\r\n'.encode())
        buf.append(f'Content-Disposition: form-data; name="file"; '
                   f'filename="{fname}"\r\n'.encode())
        buf.append(f'Content-Type: {ctype}\r\n\r\n'.encode())
        buf.append(content)
        buf.append(f'\r\n--{boundary}--\r\n'.encode())
        data = b''.join(buf)
        hdr['Content-Type'] = f'multipart/form-data; boundary={boundary}'
    elif body is not None:
        data = json.dumps(body).encode()
        hdr['Content-Type'] = 'application/json'

    r = urllib.request.Request(url, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            payload = resp.read()
            return (resp.status, payload) if raw else (resp.status, json.loads(payload))
    except urllib.error.HTTPError as e:
        payload = e.read()
        return (e.code, payload) if raw else (e.code, json.loads(payload))


def bearer(tok):
    return {'Authorization': f'Bearer {tok}'}


def main():
    print('=' * 72)
    print(f'  新增端点联调探针   base={BASE}')
    print('=' * 72)

    # ---------- 准备：管理员 + 普通用户 ----------
    print('\n0. 准备账号')
    t0 = int(time.time())
    admin_name = f'padmin{STAMP}'
    user_name = f'puser{STAMP}'

    st, j = req('POST', '/api/auth/register',
                {'username': admin_name, 'password': 'Passw0rd1',
                 'nickname': '管理员探针'})
    if j.get('code') != 0:
        print('  注册失败，终止：', j)
        return 1
    admin_tok = j['data']['access_token']
    admin_id = j['data']['user']['id']

    # 提升为管理员（直接改库，探针特权）
    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker
    from app.core.database import engine
    from app.models import User
    db = sessionmaker(bind=engine, future=True)()
    db.execute(sa.update(User).where(User.id == admin_id).values(role='admin'))
    db.commit()

    st, j = req('POST', '/api/auth/register',
                {'username': user_name, 'password': 'Passw0rd1',
                 'nickname': '用户探针'})
    user_tok = j['data']['access_token']
    user_id = j['data']['user']['id']
    check('准备：管理员与普通用户各一', bool(admin_tok) and bool(user_tok),
          f'admin#{admin_id} user#{user_id}')

    # 另建一个"他人"用户，用于跨用户权限验证
    other_name = f'pother{STAMP}'
    st, j = req('POST', '/api/auth/register',
                {'username': other_name, 'password': 'Passw0rd1'})
    other_tok = j['data']['access_token']
    other_id = j['data']['user']['id']

    # ---------- 样本图 ----------
    import glob
    base_dir = os.path.join(_ROOT, 'fish_image23', 'fish_image')
    samples = {}
    for cls in ('fish_1', 'fish_3', 'fish_21'):
        g = sorted(glob.glob(os.path.join(base_dir, cls, '*.png')))
        if g:
            samples[cls] = open(g[0], 'rb').read()
    check('准备：三张样本图', len(samples) == 3, f'{sorted(samples)}')

    # ---------- 1. 批量识别 ----------
    print('\n1. POST /api/recognize/batch 批量识别（PRD FR-RECOG-05）')
    img_ids = []
    for cls in ('fish_1', 'fish_3', 'fish_21'):
        st, j = req('POST', '/api/images',
                    files=(f'{cls}.png', samples[cls], 'image/png'),
                    headers=bearer(user_tok))
        if j.get('code') == 0:
            img_ids.append(j['data']['image']['id'])
        else:
            print(f'    ! 上传 {cls} 失败 code={j.get("code")} {j.get("message")}')
    check('批量前置：上传 3 张', len(img_ids) == 3)

    st, j = req('POST', '/api/recognize/batch',
                {'image_ids': img_ids, 'top_k': 5}, headers=bearer(user_tok))
    d = j.get('data') or {}
    check('批量识别 → 200', st == 200 and j.get('code') == 0, f'http={st}')
    check('返回 total/processed/succeeded/failed',
          all(k in d for k in ('total', 'processed', 'succeeded', 'failed')),
          f'keys={sorted(d)}')
    check('total=3 且 succeeded=3', d.get('total') == 3 and d.get('succeeded') == 3,
          f"total={d.get('total')} ok={d.get('succeeded')}")
    check('results 逐项含 image_id/code/data',
          all(k in r for r in d.get('results', []) for k in ('image_id', 'code', 'data')))
    # 三类预测正确性
    expect = {'fish_1': 0, 'fish_3': 2, 'fish_21': 20}
    got = [r['data']['class_index'] for r in d.get('results', [])]
    check('三张预测全部正确', got == [expect[c] for c in ('fish_1', 'fish_3', 'fish_21')],
          f'got={got} 期望={[expect[c] for c in ("fish_1","fish_3","fish_21")]}')
    check('登录用户批量识别逐张落库',
          all(r['data']['record_id'] for r in d.get('results', [])))

    batch_record_ids = [r['data']['record_id'] for r in d.get('results', [])]

    # 批量失败恢复：混入一个不存在的 image_id，应不影响其他项
    st, j = req('POST', '/api/recognize/batch',
                {'image_ids': [img_ids[0], 'not-a-real-id', img_ids[1]]},
                headers=bearer(user_tok))
    d2 = j.get('data') or {}
    codes = [r['code'] for r in d2.get('results', [])]
    check('批量遇坏 ID 不中断整批（第 2 项 40401，第 3 项仍成功）',
          codes == [0, 40401, 0], f'codes={codes}')
    check('HTTP 仍为 200（部分成功不算整体失败）', st == 200, f'http={st}')

    # 超上限（>9）应 40001
    st, j = req('POST', '/api/recognize/batch',
                {'image_ids': [img_ids[0]] * 10}, headers=bearer(user_tok))
    check('批量超 9 张 → 40001', j.get('code') == 40001, f"code={j.get('code')}")

    # 游客批量：额度耗尽后提前结束
    print('\n  1b. 游客批量识别的额度语义')
    gs = f'probe-guest-{STAMP}'
    GH = {'X-Guest-Session': gs}
    gimg = []
    for cls in ('fish_1', 'fish_3', 'fish_21'):
        st, j = req('POST', '/api/images',
                    files=(f'g_{cls}.png', samples[cls], 'image/png'), headers=GH)
        gimg.append(j['data']['image']['id'])
    st, j = req('POST', '/api/recognize/batch',
                {'image_ids': gimg}, headers=GH)
    gd = j.get('data') or {}
    check('游客批量：额度 3，3 张全部成功',
          gd.get('succeeded') == 3, f"ok={gd.get('succeeded')}")
    check('游客批量不落库', all(r['data']['record_id'] is None
                                for r in gd.get('results', [])))
    # 再发一批，额度已用尽 → 首项即 42901 并提前结束
    st, j = req('POST', '/api/recognize/batch',
                {'image_ids': gimg}, headers=GH)
    gd2 = j.get('data') or {}
    rs = gd2.get('results', [])
    check('游客额度用尽：提前结束（results 仅 1 项且为 42901）',
          len(rs) == 1 and rs[0]['code'] == 42901,
          f'n={len(rs)} code={rs[0]["code"] if rs else None}')
    check('游客额度用尽：processed 小于 total',
          gd2.get('processed') == 1 and gd2.get('total') == 3,
          f"processed={gd2.get('processed')} total={gd2.get('total')}")

    # ---------- 2. 单条删除 ----------
    print('\n2. DELETE /api/records/{record_id} 单条软删除')
    rid = batch_record_ids[0]
    st, j = req('GET', f'/api/records/{rid}', headers=bearer(user_tok))
    check('删除前详情可达', j.get('code') == 0)

    st, j = req('DELETE', f'/api/records/{rid}', headers=bearer(user_tok))
    check('单条删除 → 200 且 deleted=1',
          st == 200 and j.get('code') == 0 and j['data']['deleted'] == 1,
          f"http={st} code={j.get('code')} n={j.get('data', {}).get('deleted')}")

    st, j = req('GET', f'/api/records/{rid}', headers=bearer(user_tok))
    check('删除后详情 → 40401', j.get('code') == 40401, f"code={j.get('code')}")

    st, j = req('DELETE', f'/api/records/{rid}', headers=bearer(user_tok))
    check('重复删除 → 40401（幂等友好）', j.get('code') == 40401, f"code={j.get('code')}")

    # 越权：他人记录→40401（非 403，防 ID 枚举）
    rid_other = batch_record_ids[1]
    st, j = req('DELETE', f'/api/records/{rid_other}', headers=bearer(other_tok))
    check('删他人记录 → 40401（不是 403，防 ID 枚举）',
          j.get('code') == 40401 and st == 404, f"code={j.get('code')} http={st}")

    # 未登录
    st, j = req('DELETE', f'/api/records/{rid_other}')
    check('未登录删记录 → 40101', j.get('code') == 40101, f"code={j.get('code')}")

    # ---------- 3. 管理端跨用户记录 ----------
    print('\n3. GET /api/admin/records 跨用户记录列表（PRD FR-USER-08）')
    st, j = req('GET', '/api/admin/records', headers=bearer(admin_tok))
    d = j.get('data') or {}
    check('管理端列表 → 200', st == 200 and j.get('code') == 0, f'http={st}')
    check('含分页元信息', all(k in d for k in ('items', 'page', 'total', 'total_pages')))

    st, j2 = req('GET', '/api/admin/records', headers=bearer(user_tok))
    check('普通用户访问管理端列表 → 40301（角色不足）',
          j2.get('code') == 40301 and st == 403, f"code={j2.get('code')} http={st}")

    # 跨用户可见性：管理员能看到 other 用户的记录
    # 【注意】用 other 自己的图，不能借用 user 的图 ——
    # 有 owner 的图受归属校验保护（他人访问一律 40401），这是设计行为。
    st, jg = req('POST', '/api/images',
                 files=('other.png', samples['fish_1'], 'image/png'),
                 headers=bearer(other_tok))
    if not check('他人用户上传自己的图', jg.get('code') == 0,
                 f"code={jg.get('code')}"):
        other_rid = None
    else:
        st, jo = req('POST', '/api/recognize',
                     {'image_id': jg['data']['image']['id']},
                     headers=bearer(other_tok))
        if not check('他人用户识别成功（跨用户数据准备）',
                     jo.get('code') == 0 and jo.get('data'),
                     f"code={jo.get('code')} msg={jo.get('message')}"):
            other_rid = None
        else:
            other_rid = jo['data']['record_id']

    # 反向验证：他人访问 user 的图必须 40401（归属校验）
    st, jx = req('POST', '/api/recognize', {'image_id': img_ids[0]},
                 headers=bearer(other_tok))
    check('他人识别我的图 → 40401（归属校验生效）',
          jx.get('code') == 40401, f"code={jx.get('code')}")

    if other_rid:
        st, j = req('GET', f'/api/admin/records?user_id={other_id}',
                    headers=bearer(admin_tok))
        items = (j.get('data') or {}).get('items', [])
        check('按 user_id 过滤可看到他人记录',
              any(x['id'] == other_rid for x in items), f'n={len(items)}')

    # ---------- 4. 管理端删除任意记录 ----------
    print('\n4. DELETE /api/admin/records/{record_id} 删任意用户记录')
    if not other_rid:
        check('管理员删他人记录 → 200 且 deleted=1', False, '前置未就绪')
    else:
        st, j = req('DELETE', f'/api/admin/records/{other_rid}',
                    headers=bearer(admin_tok))
        check('管理员删他人记录 → 200 且 deleted=1',
              st == 200 and j.get('code') == 0 and j['data']['deleted'] == 1,
              f"code={j.get('code')} n={j.get('data', {}).get('deleted')}")

        st, j = req('GET', f'/api/records/{other_rid}', headers=bearer(admin_tok))
        check('管理员视角：已删除记录 → 40401', j.get('code') == 40401)

    st, j = req('DELETE', f'/api/admin/records/{other_rid}',
                headers=bearer(user_tok))
    check('普通用户调管理端删除 → 40301',
          j.get('code') == 40301 and st == 403, f"code={j.get('code')}")

    # ---------- 5. 既有端点未回归 ----------
    print('\n5. 既有端点抽样回归')
    st, j = req('GET', '/api/records?page=1&page_size=5', headers=bearer(user_tok))
    check('GET /api/records（主路径）仍正常', j.get('code') == 0,
          f"total={j.get('data', {}).get('total')}")

    st, j = req('GET', '/api/history?page=1&page_size=5', headers=bearer(user_tok))
    check('GET /api/history（别名）仍正常', j.get('code') == 0,
          f"total={j.get('data', {}).get('total')}")

    st, j = req('DELETE', '/api/records',
                {'record_ids': batch_record_ids[2:]}, headers=bearer(user_tok))
    check('DELETE /api/records 批量删除仍正常',
          j.get('code') == 0 and j['data']['deleted'] >= 1,
          f"n={j.get('data', {}).get('deleted')}")

    st, j = req('GET', '/api/admin/config', headers=bearer(admin_tok))
    check('GET /api/admin/config 仍正常', j.get('code') == 0)

    st, j = req('PUT', '/api/admin/config', {'config': {'guest_quota': '3'}},
                headers=bearer(admin_tok))
    check('PUT /api/admin/config 仍正常', j.get('code') == 0,
          f"updated={len(j.get('data', {}).get('updated', []))}")

    # ---------- 5b. V1.1 新增端点专项 ----------
    print('\n5b. V1.1 新增端点')

    # GET /api/guest/quota —— 游客（未带任何令牌）
    st, j = req('GET', '/api/guest/quota')
    check('GET /api/guest/quota 游客 → 200', j.get('code') == 0, f'http={st}')
    _q = j.get('data') or {}
    check('字段恰为 limit/used/remaining', set(_q) == {'limit', 'used', 'remaining'},
          f'{sorted(_q)}')
    check('未泄漏内部字段 is_guest/known',
          'is_guest' not in _q and 'known' not in _q)
    check('limit 与配置项一致（3）', _q.get('limit') == 3, f"{_q.get('limit')}")

    # GET /api/guest/quota —— 已登录应全 0
    st, j = req('GET', '/api/guest/quota', headers=bearer(user_tok))
    check('已登录 → 三者均为 0', (j.get('data') or {}) ==
          {'limit': 0, 'used': 0, 'remaining': 0}, f"{j.get('data')}")

    # DELETE /api/images/{image_id}
    # 未认证：用一个真实存在的图 ID，确保拦截发生在鉴权层而非查库层
    st, j = req('DELETE', f'/api/images/{img_ids[0]}')
    check('DELETE /api/images 未认证 → 40101',
          j.get('code') == 40101, f"code={j.get('code')}")

    st, j = req('DELETE', '/api/images/00000000-0000-0000-0000-000000000000',
                headers=bearer(user_tok))
    check('DELETE 不存在的图 → 40401', j.get('code') == 40401,
          f"code={j.get('code')}")

    # 越权：他人删除我的图（先于删除，图还在）
    st, j = req('DELETE', f'/api/images/{img_ids[0]}', headers=bearer(other_tok))
    check('他人删除我的图 → 40401（非 403，防枚举）',
          j.get('code') == 40401 and st == 404,
          f"code={j.get('code')} http={st}")

    # 已识别的图应拒绝删除（避免级联丢失历史）
    st, j = req('DELETE', f'/api/images/{img_ids[0]}', headers=bearer(user_tok))
    check('DELETE 已识别图片 → 42201', j.get('code') == 42201,
          f"code={j.get('code')} msg={j.get('message', '')[:30]}")

    # 未识别的图可以删除
    # 【坑】create_asset 会按 (user_id, content_hash) 复用资产：
    # 若在这里重传 fish_1/fish_3，拿回的会是先前那张已识别的图（reused=True），
    # 删除时必然 42201 —— 这是设计行为，不是缺陷。
    # 故必须上传一张**本会话未用过**的图。取一张已被识别的图，翻转末尾字节
    # 并修正 PNG IEND 校验，使 content_hash 变化而图像仍可解析。
    import zlib
    base_png = bytearray(samples['fish_1'])
    end = base_png.rfind(b'\x00\x00\x00\x00IEND')
    if end > 0:
        # IEND 前的 CRC 4 字节，改写为合法 CRC（内容不变，仅字节翻新）
        crc = zlib.crc32(bytes(base_png[end + 4:end + 8])) & 0xFFFFFFFF
        base_png[end + 12:end + 16] = crc.to_bytes(4, 'big')
    fresh_bytes = bytes(base_png)
    st, j = req('POST', '/api/images',
                files=('cleanup.png', fresh_bytes, 'image/png'),
                headers=bearer(user_tok))
    fresh_img = ((j.get('data') or {}).get('image') or {}).get('id')
    check('清理用图上传成功', bool(fresh_img), f'id={fresh_img}')

    if fresh_img:
        st, j = req('DELETE', f'/api/images/{fresh_img}', headers=bearer(user_tok))
        check('DELETE 未识别图片 → 200', j.get('code') == 0,
              f"code={j.get('code')} msg={j.get('message', '')[:40]}")

        st, j = req('GET', f'/api/images/{fresh_img}/content',
                    headers=bearer(user_tok))
        check('删除后再取原图 → 40401', j.get('code') == 40401,
              f"code={j.get('code')}")
    else:
        check('DELETE 未识别图片 → 200', False, '前置上传失败')
        check('删除后再取原图 → 40401', False, '前置上传失败')

    # ---------- 清理 ----------
    print('\n6. 清理探针数据')
    from app.models import ImageAsset, RecognitionRecord, GuestUsage, OperationLog
    try:
        for uid in (admin_id, user_id, other_id):
            for r in db.scalars(sa.select(RecognitionRecord).where(
                    RecognitionRecord.user_id == uid)):
                db.delete(r)
            for a in db.scalars(sa.select(ImageAsset).where(ImageAsset.user_id == uid)):
                db.delete(a)
            for lg in db.scalars(sa.select(OperationLog).where(OperationLog.user_id == uid)):
                lg.user_id = None
            u = db.get(User, uid)
            if u:
                db.delete(u)
        db.commit()
        check('探针账号与数据已清理', True)
    except Exception as e:
        db.rollback()
        check('探针账号与数据已清理', False, f'{type(e).__name__}: {e}')

    print()
    print('=' * 72)
    print(f'  合计  通过 {PASS} / 失败 {FAIL}')
    if FAILS:
        print('  失败项：')
        for f in FAILS:
            print(f'    - {f}')
    print('=' * 72)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
