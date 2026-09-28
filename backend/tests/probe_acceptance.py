# -*- coding: utf-8 -*-
"""M6 · 端到端联调与验收探针（对运行中的真实服务）

与既有探针的分工（互不替代，本脚本是最后一层）：
    test_e2e.py             TestClient + 临时库     → 代码逻辑与契约
    test_nfr_audit.py       D7 结构 / NFR 审计
    probe_new_endpoints.py  新增端点专项
    probe_live_server.py    live HTTP 冒烟（39 项）
    **probe_acceptance.py** ← 本脚本：验收级全链路 + PRD §9 性能分段 + 拓扑一致性

本脚本做四件既有探针没做的事：
    ① **拓扑一致性**：核对「文档声明 / 配置 / 实际运行」三者的端口与跨域口径；
    ② **业务全链路**：游客（额度 3→0→42901）与注册用户（上传→识别→落库→历史→候选→导出→删除）
       两条完整旅程，逐环节断言，而非单端点冒烟；
    ③ **PRD 第 9 章端到端 ≤3 s 的分段实证**：把 3000 ms 预算拆成
       上传 / 预处理 / 推理 / 落库 / 渲染 五段，逐段给实测值（HTTP 段实测 + 阶段微基准）；
    ④ **善后**：删除本轮创建的账号与图像（既有 probe_live_server.py 无 teardown，
       每跑一次留一个账号 —— 本脚本补上这个缺口）。

前置：后端 127.0.0.1:8000、前端 dev server 127.0.0.1:5180 均已运行。

用法：
    C:\\python\\python.exe backend/tests/probe_acceptance.py
    C:\\python\\python.exe backend/tests/probe_acceptance.py --samples 12
    C:\\python\\python.exe backend/tests/probe_acceptance.py --skip-stage-bench --no-cleanup

退出码：0 全通过；1 有失败项；2 服务不可达。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import random
import statistics
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get('SEATONG_BASE', 'http://127.0.0.1:8000')
FRONTEND = os.environ.get('SEATONG_FRONTEND', 'http://127.0.0.1:5180')
ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / 'fish_image23' / 'fish_image'

# 服务端限流为 60 次/分钟（错误码 42902）。本脚本对**每一次**请求限速，
# 使长期速率稳定在 ~52 次/分钟，从源头避免触发限流（而非靠失败后退避）。
MIN_GAP_S = 1.15
_last_req = [0.0]

PASS = {'n': 0}
FAILS: list[str] = []
NOTES: list[str] = []


# ---------------------------------------------------------------- 基础设施

def check(label: str, cond: bool, extra: str = '') -> bool:
    if cond:
        PASS['n'] += 1
        print(f'  \u2713 {label}' + (f'  {extra}' if extra else ''))
    else:
        FAILS.append(label)
        print(f'  \u2717 {label}' + (f'  {extra}' if extra else ''))
    return bool(cond)


def note(text: str) -> None:
    NOTES.append(text)
    print(f'  \u2013 {text}')


def _throttle() -> None:
    dt = time.perf_counter() - _last_req[0]
    if dt < MIN_GAP_S:
        time.sleep(MIN_GAP_S - dt)
    _last_req[0] = time.perf_counter()


def _http(method: str, url: str, body=None, headers=None, raw=False,
          timeout: int = 90):
    """返回 (status, payload, headers_lower)。payload 为 dict 或 bytes。"""
    hdr = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        hdr['Content-Type'] = 'application/json'
    rq = urllib.request.Request(url, data=data, headers=hdr, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            b = r.read()
            payload = b if raw else json.loads(b.decode('utf-8'))
            return r.status, payload, {k.lower(): v for k, v in r.headers.items()}, (time.perf_counter() - started) * 1000
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            payload = b if raw else json.loads(b.decode('utf-8'))
        except Exception:
            payload = b
        return e.code, payload, {k.lower(): v for k, v in e.headers.items()}, (time.perf_counter() - started) * 1000


def api(method: str, path: str, body=None, headers=None, raw=False,
        tries: int = 4):
    """带限速与 42902 退避的请求。返回 (status, payload, headers, wall_ms)。"""
    st = pl = hd = None
    wall = 0.0
    for i in range(tries):
        _throttle()
        st, pl, hd, ms = _http(method, BASE + path, body, headers, raw)
        wall += ms
        code = pl.get('code') if isinstance(pl, dict) else None
        if st == 429 or code == 42902:
            if i < tries - 1:
                time.sleep(3.0)
                continue
        return st, pl, hd, wall
    return st, pl, hd, wall


def upload(path: pathlib.Path, headers: dict, tries: int = 4):
    """multipart 上传。返回 (status, payload, headers, wall_ms)。"""
    raw = path.read_bytes()
    bnd = '----seatongaccept'
    body = (
        f'--{bnd}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{path.name}"\r\nContent-Type: image/png\r\n\r\n'
    ).encode('utf-8') + raw + f'\r\n--{bnd}--\r\n'.encode('utf-8')
    hdr = {'Content-Type': f'multipart/form-data; boundary={bnd}', **headers}
    return _upload_impl(body, hdr, tries)


def _upload_impl(body: bytes, hdr: dict, tries: int):
    st = pl = hd = None
    wall = 0.0
    for i in range(tries):
        _throttle()
        rq = urllib.request.Request(BASE + '/api/images', data=body,
                                    method='POST', headers=hdr)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(rq, timeout=90) as r:
                st, pl, hd = r.status, json.loads(r.read().decode('utf-8')), \
                    {k.lower(): v for k, v in r.headers.items()}
        except urllib.error.HTTPError as e:
            st = e.code
            hd = {k.lower(): v for k, v in e.headers.items()}
            try:
                pl = json.loads(e.read().decode('utf-8'))
            except Exception:
                pl = {}
        wall += (time.perf_counter() - t0) * 1000
        if (st == 429 or (isinstance(pl, dict) and pl.get('code') == 42902)) and i < tries - 1:
            time.sleep(3.0)
            continue
        return st, pl, hd, wall
    return st, pl, hd, wall


def wait_ready(timeout: int = 60) -> bool:
    for _ in range(timeout):
        try:
            urllib.request.urlopen(BASE + '/api/health', timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def pct(vals: list[float], q: float) -> float:
    """简单分位数（最近秩法），q ∈ [0,1]。"""
    if not vals:
        return 0.0
    s = sorted(vals)
    k = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[k]


def stat(vals: list[float]) -> dict:
    if not vals:
        return {'n': 0}
    return {
        'n': len(vals),
        'p50': round(pct(vals, 0.50), 1),
        'p95': round(pct(vals, 0.95), 1),
        'max': round(max(vals), 1),
        'min': round(min(vals), 1),
        'mean': round(statistics.fmean(vals), 1),
    }


def sample_images() -> list[tuple[int, pathlib.Path]]:
    """23 类各抽 1 张（第一张），用于正确性断言。"""
    out = []
    for n in range(1, 24):
        files = sorted(glob.glob(str(DATA / f'fish_{n}' / '*.png')))
        if files:
            out.append((n, pathlib.Path(files[0])))
    return out


def rotating_images(count: int) -> list[tuple[int, pathlib.Path]]:
    """按类别轮转取图，避免性能样本集中在头部类（长尾数据集的采样纪律）。"""
    buckets: dict[int, list[str]] = {}
    for n in range(1, 24):
        fs = sorted(glob.glob(str(DATA / f'fish_{n}' / '*.png')))
        if fs:
            buckets[n] = fs
    keys = sorted(buckets)
    out = []
    for i in range(count):
        n = keys[i % len(keys)]
        fs = buckets[n]
        out.append((n, pathlib.Path(fs[(i // len(keys)) % len(fs)])))
    return out


# ---------------------------------------------------------------- 阶段微基准

def stage_micro_bench(samples: list[tuple[int, pathlib.Path]]) -> dict:
    """把「预处理」与「纯前向」从服务端 duration_ms 里拆出来。

    duration_ms = 预处理 + H2D + 前向 + topk（见 app/services/inference.py）。
    作为整体它已被真实 HTTP 实测覆盖；这里额外做**同代码路径**的阶段微基准，
    以便与 PRD §9 的「预处理 200 ms / 推理 2000 ms」逐段对照。

    复用单一真源：预处理用 ml/dataset/preprocess.preprocess_for_inference，
    模型用 ml/optimize/common.load_baseline()（即 train.build_model + 基线权重），
    不另写第二份实现。
    """
    try:
        sys.path.insert(0, str(ROOT / 'ml'))
        sys.path.insert(0, str(ROOT / 'ml' / 'optimize'))
        import torch
        import common as optcommon          # ml/optimize/common.py
        from dataset.preprocess import preprocess_for_inference

        model, cfg, _ckpt = optcommon.load_baseline()
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model = model.to(device).eval()

        pre_ms: list[float] = []
        fwd_ms: list[float] = []
        payloads = [(n, p.read_bytes()) for n, p in samples]

        # 预热（CUDA kernel 首启会污染首轮）
        with torch.inference_mode():
            t = preprocess_for_inference(payloads[0][1]).to(device)
            for _ in range(5):
                model(t)

        with torch.inference_mode():
            for _n, raw in payloads:
                t0 = time.perf_counter()
                tensor = preprocess_for_inference(raw)
                pre_ms.append((time.perf_counter() - t0) * 1000)

                t1 = time.perf_counter()
                x = tensor.to(device, non_blocking=True)
                logits = model(x)
                torch.softmax(logits.float(), dim=1)[0].topk(5)
                if device == 'cuda':
                    torch.cuda.synchronize()
                fwd_ms.append((time.perf_counter() - t1) * 1000)

        return {
            'device': device,
            'n': len(payloads),
            'preprocess_ms': stat(pre_ms),
            'forward_ms': stat(fwd_ms),
        }
    except Exception as e:                      # 微基准失败不应让整轮验收失败
        note(f'阶段微基准跳过：{type(e).__name__}: {e}')
        return {'error': f'{type(e).__name__}: {e}'}


# ---------------------------------------------------------------- 各章节

def sec_topology() -> dict:
    print('\n1. 服务可达性与拓扑口径')
    ok = wait_ready(30)
    check('后端 /api/health 可达', ok, BASE)
    if not ok:
        return {}

    st, j, h, _ = api('GET', '/api/health')
    d = j['data']
    check('健康检查信封 code=0', st == 200 and j.get('code') == 0)
    check('X-Request-Id 响应头存在', bool(h.get('x-request-id')), h.get('x-request-id', ''))
    check('X-Process-Time-Ms 响应头存在', bool(h.get('x-process-time-ms')),
          h.get('x-process-time-ms', '') + ' ms')
    check('信封 request_id 与响应头一致', j.get('request_id') == h.get('x-request-id'))
    check('DB PRAGMA foreign_keys = 1', d['db_pragmas'].get('foreign_keys') == 1,
          json.dumps(d['db_pragmas'], ensure_ascii=False))
    m = d['model']
    check('模型 ready', m['ready'] is True, f"device={m.get('device')}")
    check('运行在 CUDA', m.get('device') == 'cuda', str(m.get('device')))
    check('num_classes=23 / img_size=224', m['num_classes'] == 23 and m['img_size'] == 224)
    check('权重文件存在', m.get('ckpt_exists') is True)
    tm = m.get('trained_metrics') or {}
    check('冻存 acc ≥ 0.85（PRD）', tm.get('accuracy', 0) >= 0.85, f"acc={tm.get('accuracy')}")
    check('冻存 macro_f1 ≥ 0.82（PRD）', tm.get('macro_f1', 0) >= 0.82,
          f"macro_f1={tm.get('macro_f1')}")

    # 端点集合口径：D8 §11.2 声明 38 个（35 主路径 + 3 别名），此处按 (方法,路径) 对核数
    try:
        with urllib.request.urlopen(BASE + '/openapi.json', timeout=10) as r:
            spec = json.loads(r.read().decode('utf-8'))
        spec = spec.get('data', spec)
        paths = spec.get('paths', {})
        pairs = [(mth.upper(), p) for p, ops in paths.items() for mth in ops]
        check('openapi 路径数 = 32', len(paths) == 32, f'{len(paths)} 条路径')
        check('端点（方法+路径）对数 = 38', len(pairs) == 38, f'{len(pairs)} 对')
    except Exception as e:
        check('openapi 可读取', False, f'{type(e).__name__}: {e}')

    # 前端 dev server
    try:
        with urllib.request.urlopen(FRONTEND + '/', timeout=8) as r:
            html = r.read().decode('utf-8', 'ignore')
        check('前端 dev server 可达', r.status == 200, FRONTEND)
        check('前端页面标题为「海瞳鱼鉴」', '海瞳鱼鉴' in html,
              html.split('<title>')[-1].split('</title>')[0] if '<title>' in html else '—')
        # 5173 归属核对：确认本项目服务确实未占用 5173（该端口属同机另一项目）
        try:
            with urllib.request.urlopen('http://127.0.0.1:5173/', timeout=5) as r2:
                other = r2.read().decode('utf-8', 'ignore')
            title = (other.split('<title>')[-1].split('</title>')[0]
                     if '<title>' in other else '—')
            check('端口隔离正确：5173 上不是本项目', '海瞳鱼鉴' not in other, title)
        except Exception as e:
            note(f'5173 未服务（不影响本次验收）：{type(e).__name__}')
    except Exception as e:
        check('前端 dev server 可达', False, f'{type(e).__name__}: {e}')

    # 跨域口径：直接以 Origin: <前端源> 打后端，看是否放行
    cors = {}
    for origin in (FRONTEND.replace('127.0.0.1', 'localhost'), 'http://127.0.0.1:5180',
                   'http://localhost:5173'):
        try:
            rq = urllib.request.Request(BASE + '/api/health', headers={'Origin': origin})
            with urllib.request.urlopen(rq, timeout=8) as r:
                hl = {k.lower(): v for k, v in r.headers.items()}
            cors[origin] = hl.get('access-control-allow-origin')
        except Exception as e:
            cors[origin] = f'ERR {type(e).__name__}'
    check('CORS 放行前端源 5180', cors.get('http://localhost:5180') == 'http://localhost:5180',
          f"ACAO={cors.get('http://localhost:5180')}")
    if cors.get('http://localhost:5180') is None:
        note('CORS 未放行 5180：配置已修订（config.py/main.py），'
             '但运行中的后端进程为修订前启动，需重启后端方生效；'
             'dev 链路由 Vite 代理转发，故不影响本机联调。')
    return {'cors': cors, 'health': d}


def sec_guest() -> dict:
    print('\n2. 游客全链路（免登录 3 次额度）')
    gs = f'acc-guest-{random.randint(100000, 999999)}'
    GH = {'X-Guest-Session': gs}
    st, j, _h, _ = api('GET', '/api/guest/quota', None, GH)
    check('GET /api/guest/quota → 200', st == 200 and j.get('code') == 0)
    q = j['data']
    check('额度字段名为 limit（D8 契约）', 'limit' in q, json.dumps(q, ensure_ascii=False))
    check('游客初始 limit=3 / remaining=3',
          q.get('limit') == 3 and q.get('remaining') == 3, json.dumps(q, ensure_ascii=False))

    st, j, _h, _ = api('GET', '/api/users/me', None, GH)
    check('游客 /api/users/me → is_guest=True', j['data'].get('is_guest') is True)
    check('内嵌 guest_quota.quota=3（与 limit 字段名有意不同）',
          (j['data'].get('guest_quota') or {}).get('quota') == 3,
          json.dumps(j['data'].get('guest_quota'), ensure_ascii=False))

    n, p = sample_images()[0]
    st, up, _h, up_ms = upload(p, GH)
    check('游客上传 → 200 且 code=0', st == 200 and up.get('code') == 0,
          f'fish_{n} / {p.name} / {up_ms:.0f} ms')
    iid = up['data']['image']['id']

    st, j, _h, _ = api('GET', '/api/guest/quota', None, GH)
    check('上传不消耗额度（remaining 仍为 3）', j['data'].get('remaining') == 3,
          json.dumps(j['data'], ensure_ascii=False))

    results = []
    for k in range(3):
        st, rc, _h, wall = api('POST', '/api/recognize', {'image_id': iid, 'top_k': 5}, GH)
        if rc.get('code') != 0:
            results.append(None)
            break
        results.append(rc['data'])
    check('游客连续识别 3 次全部成功', all(r is not None for r in results) and len(results) == 3)
    if results and results[0]:
        d0 = results[0]
        check('游客识别不落库（record_id 为空）', d0.get('record_id') is None,
              f"record_id={d0.get('record_id')}")
        check('Top-5 候选完整（5 条，rank 1..5）',
              len(d0['candidates']) == 5 and
              [c['rank'] for c in d0['candidates']] == [1, 2, 3, 4, 5])
        check('候选置信度单调不增',
              all(d0['candidates'][i]['confidence'] >= d0['candidates'][i + 1]['confidence']
                  for i in range(4)))
        check('置信度在 [0,1] 且 Top-1 与候选首位一致',
              0 <= d0['confidence'] <= 1 and
              d0['candidates'][0]['class_index'] == d0['class_index'])
        check('物种知识库随识别结果返回（形态/习性齐备）',
              bool(d0.get('species') and d0['species'].get('morphology')
                   and d0['species'].get('habit')),
              (d0.get('species') or {}).get('cn_name', '—'))
        check('识别结果含模型版本号', bool(d0.get('model_version')),
              str(d0.get('model_version')))
    if results and results[-1]:
        gq = results[-1].get('guest_quota') or {}
        check('第 3 次识别后 remaining=0', gq.get('remaining') == 0,
              json.dumps(gq, ensure_ascii=False))

    st, rc, _h, _ = api('POST', '/api/recognize', {'image_id': iid}, GH)
    check('第 4 次识别被拒 → 42901', st == 429 and rc.get('code') == 42901,
          f"http={st} code={rc.get('code')}")

    return {'session': gs, 'image_id': iid,
            'recognize_sample': (results[0] if results and results[0] else None)}


def sec_user(admin_tok: str | None) -> dict:
    print('\n3. 注册用户全链路（登录态）')
    uname = f'acc{random.randint(100000, 999999)}'
    pwd = 'Passw0rd1'
    st, j, _h, _ = api('POST', '/api/auth/register',
                       {'username': uname, 'password': pwd, 'nickname': '验收探针'})
    if j.get('code') != 0:
        check('注册 → 200', False, f'code={j.get("code")} msg={j.get("message")}')
        return {}
    check('注册 → 200', st == 200 and j.get('code') == 0, f'user={uname}')
    uid = j['data'].get('user', {}).get('id')
    T = {'Authorization': 'Bearer ' + j['data']['access_token']}

    st, j2, _h, _ = api('POST', '/api/auth/login', {'username': uname, 'password': pwd})
    check('登录 → 200 且签发令牌', st == 200 and j2.get('code') == 0
          and bool(j2['data'].get('access_token')))
    check('登录返回 refresh_token', bool(j2['data'].get('refresh_token')))
    T = {'Authorization': 'Bearer ' + j2['data']['access_token']}

    st, j3, _h, _ = api('POST', '/api/auth/refresh',
                        {'refresh_token': j2['data']['refresh_token']})
    check('刷新令牌 → 200', st == 200 and j3.get('code') == 0)

    st, me, _h, _ = api('GET', '/api/users/me', None, T)
    check('登录用户 is_guest=False', me['data'].get('is_guest') is False)
    check('登录用户体不返回游客额度',
          (me['data'].get('guest_quota') or {}) == {},
          json.dumps(me['data'].get('guest_quota'), ensure_ascii=False))

    # 上传 + 识别 + 落库
    created_imgs: list[str] = []
    n, p = sample_images()[2]          # fish_3
    st, up, _hu, up_ms = upload(p, T)
    check('登录上传 → 200', st == 200 and up.get('code') == 0, f'{up_ms:.0f} ms')
    iid = up['data']['image']['id']
    created_imgs.append(iid)

    st, rc, hr, rec_wall = api('POST', '/api/recognize', {'image_id': iid, 'top_k': 5}, T)
    check('登录识别 → 200', st == 200 and rc.get('code') == 0)
    d = rc['data']
    rid = d['record_id']
    check('识别命中（fish_3 → class_index=2）', d['class_index'] == 2,
          f"idx={d['class_index']} {d['cn_name']} conf={d['confidence']:.4f}")
    check('登录识别落库（record_id 非空）', bool(rid), f'record_id={rid}')
    check('响应含服务端耗时 duration_ms', isinstance(d.get('duration_ms'), int),
          f"duration_ms={d.get('duration_ms')}")

    st, ls, _h, _ = api('GET', '/api/records', None, T)
    check('历史列表 → 200 且含该记录', st == 200 and ls['data']['total'] >= 1,
          f'total={ls["data"]["total"]}')
    ids = [it['id'] for it in ls['data']['items']]
    check('新记录出现在列表首位（默认按时间倒序）', bool(ids) and ids[0] == rid)
    it0 = ls['data']['items'][0]
    check('列表项字段齐备（id/缩略图/物种/置信度/状态）',
          all(k in it0 for k in ('id', 'class_index', 'cn_name', 'confidence',
                                 'status', 'thumb_url', 'duration_ms')),
          json.dumps({k: it0[k] for k in ('id', 'cn_name', 'confidence', 'status')},
                     ensure_ascii=False))
    check('record.status 取值合法（success/interrupted）',
          it0['status'] in ('success', 'interrupted'), it0['status'])

    st, dt, _h, _ = api('GET', f'/api/records/{rid}', None, T)
    check('记录详情 → 200 且四段齐备（record/image/species/candidates）',
          st == 200 and all(k in dt['data'] for k in
                            ('record', 'image', 'species', 'candidates')),
          ','.join(sorted(dt['data'].keys())))
    check('详情内 species 与识别结果一致',
          (dt['data']['species'] or {}).get('class_index') == d['class_index'])

    st, cd, _h, _ = api('GET', f'/api/results/{rid}/candidates', None, T)
    check('Top-5 候选独立端点 → 200 且 5 条', st == 200 and len(cd['data']) == 5,
          f"n={len(cd['data'])}")

    st, csvb, hcsv, _ = api('GET', '/api/records/export', None, T, raw=True)
    check('导出 CSV → 200', st == 200)
    check('CSV 带 UTF-8 BOM（Excel 中文不乱码）',
          isinstance(csvb, bytes) and csvb[:3] == b'\xef\xbb\xbf')
    check('CSV 含中文表头', isinstance(csvb, bytes) and '中文名'.encode('utf-8') in csvb)
    check('CSV 为附件下载（Content-Disposition: attachment）',
          'attachment' in hcsv.get('content-disposition', ''),
          hcsv.get('content-disposition', ''))
    check('CSV 未被 JSON 信封包裹', isinstance(csvb, bytes) and not csvb.lstrip().startswith(b'{'))

    # 缩略图与原图内容端点（缩略图服务端统一转 JPEG：image_service.thumb_bytes）
    st, th, hth, _ = api('GET', f'/api/images/{iid}/thumb', None, T, raw=True)
    check('缩略图 → 200 且为 JPEG 字节',
          st == 200 and isinstance(th, bytes) and th[:3] == b'\xff\xd8\xff',
          f"{len(th) if isinstance(th, bytes) else 0} bytes / "
          f"{hth.get('content-type', '—')}")
    st, og, _h, _ = api('GET', f'/api/images/{iid}/content', None, T, raw=True)
    check('原图 → 200 且为图像字节',
          st == 200 and isinstance(og, bytes) and og[:8] == b'\x89PNG\r\n\x1a\n',
          f"{len(og) if isinstance(og, bytes) else 0} bytes")

    # 批量识别（FR-RECOG-05）
    imgs = []
    for n2, p2 in sample_images()[5:8]:      # fish_6,7,8
        st, u2, _h2, _ = upload(p2, T)
        if u2.get('code') == 0:
            imgs.append((n2, u2['data']['image']['id']))
            created_imgs.append(u2['data']['image']['id'])
    st, bj, _h, _ = api('POST', '/api/recognize/batch',
                        {'image_ids': [i for _n2, i in imgs], 'top_k': 5}, T)
    check('批量识别 → 200', st == 200 and bj.get('code') == 0)
    bd = bj['data']
    check('批量结果逐项返回且计数自洽',
          bd['total'] == len(imgs) and bd['processed'] == len(imgs)
          and bd['succeeded'] + bd['failed'] == bd['processed'],
          f"total={bd['total']} ok={bd['succeeded']} fail={bd['failed']}")
    hit_pairs = [(n2, r['data']['class_index'] if r.get('data') else None)
                 for (n2, _i), r in zip(imgs, bd['results'])]
    check('批量识别逐张命中', all(ci == n2 - 1 for n2, ci in hit_pairs),
          ', '.join(f'fish_{n2}→{ci}' for n2, ci in hit_pairs))
    check('批量识别同样落库', all(r['data'].get('record_id') for r in bd['results']
                                  if r.get('data')))

    # 单条删除（PRD FR-HISTORY 单条删除入口）
    st, dj, _h, _ = api('DELETE', f'/api/records/{rid}', None, T)
    check('删除单条记录 → 200', st == 200 and dj.get('code') == 0)
    st, _j, _h, _ = api('GET', f'/api/records/{rid}', None, T)
    check('删除后详情 → 40401', st == 404 and _j.get('code') == 40401,
          f'http={st} code={_j.get("code")}')

    # 图像删除（D8 §6.5 语义：已产生识别记录的图不可删 → 42201，防级联丢历史；
    # 记录删除是软删除，行仍在，故上述 rid 删除后该图依旧 42201）
    st, ij, _h, _ = api('DELETE', f'/api/images/{iid}', None, T)
    check('删除已识别的图 → 42201（防级联丢历史）',
          st == 422 and ij.get('code') == 42201,
          f"http={st} code={ij.get('code')}")
    n3, p3 = sample_images()[9]        # fish_10，未识别
    st, up2, _h2, _ = upload(p3, T)
    if up2.get('code') == 0:
        iid2 = up2['data']['image']['id']
        st, ij2, _h2, _ = api('DELETE', f'/api/images/{iid2}', None, T)
        check('删除未识别的图 → 200', st == 200 and ij2.get('code') == 0,
              f'fish_{n3} / http={st} code={ij2.get("code")}')

    return {'username': uname, 'password': pwd, 'user_id': uid,
            'images': created_imgs, 'recognize_wall_ms': round(rec_wall, 1),
            'server_duration_ms': d.get('duration_ms'),
            'server_proc_ms': float(hr.get('x-process-time-ms') or 0)}


def sec_errors(admin_tok: str | None) -> None:
    print('\n4. 鉴权与边界（真实服务）')
    st, j, _h, _ = api('GET', '/api/records')
    check('未认证访问历史 → 401 / 40101',
          st == 401 and j.get('code') == 40101, f'http={st} code={j.get("code")}')
    st, j, _h, _ = api('GET', '/api/records', None,
                       {'Authorization': 'Bearer not-a-real-token'})
    check('伪造令牌 → 401 / 40101', st == 401 and j.get('code') == 40101,
          f'http={st} code={j.get("code")}')
    st, j, _h, _ = api('POST', '/api/recognize', {'image_id': 'no-such-uuid'},
                       {'X-Guest-Session': 'acc-err-1'})
    check('识别不存在的图 → 404 / 40401',
          st == 404 and j.get('code') == 40401, f'http={st} code={j.get("code")}')
    st, j, _h, _ = api('GET', '/api/nonexistent-route')
    check('未知路由 → 404 / 40401', st == 404 and j.get('code') == 40401,
          f'http={st} code={j.get("code")}')
    st, j, _h, _ = api('POST', '/api/recognize', {})
    check('参数缺失 → 400 / 40001（非 FastAPI 默认 422）',
          st == 400 and j.get('code') == 40001, f'http={st} code={j.get("code")}')
    st, j, _h, _ = api('GET', '/api/species/999')
    check('物种越界 → 4xx 业务码', st in (400, 404) and j.get('code') in (40001, 40401),
          f'http={st} code={j.get("code")}')

    uname = f'accerr{random.randint(100000, 999999)}'
    st, j, _h, _ = api('POST', '/api/auth/register',
                       {'username': uname, 'password': 'Passw0rd1'})
    if j.get('code') == 0:
        T = {'Authorization': 'Bearer ' + j['data']['access_token']}
        st, j2, _h, _ = api('GET', '/api/admin/stats', None, T)
        check('普通用户访问管理端点 → 403 / 40301',
              st == 403 and j2.get('code') == 40301, f'http={st} code={j2.get("code")}')
        # 他人资源：另一用户读取该用户的记录 → 40401（防 ID 枚举，非 403）
        st, j3, _h, _ = api('GET', '/api/records', None, T)
        if j3.get('data', {}).get('items'):
            other_id = j3['data']['items'][0]['id']
            u2 = f'accother{random.randint(100000, 999999)}'
            st, j4, _h, _ = api('POST', '/api/auth/register',
                                {'username': u2, 'password': 'Passw0rd1'})
            if j4.get('code') == 0:
                T2 = {'Authorization': 'Bearer ' + j4['data']['access_token']}
                st, j5, _h, _ = api('GET', f'/api/records/{other_id}', None, T2)
                check('访问他人记录 → 404 / 40401（防 ID 枚举，非 403）',
                      st == 404 and j5.get('code') == 40401,
                      f'http={st} code={j5.get("code")}')
                if admin_tok:
                    api('DELETE', f'/api/admin/users/{j4["data"]["user"]["id"]}', None, {'Authorization': admin_tok})
        if admin_tok:
            api('DELETE', f'/api/admin/users/{j["data"]["user"]["id"]}', None, {'Authorization': admin_tok})

    # 上传体积 / 类型（413 / 415 分段）
    big = b'\x89PNG\r\n\x1a\n' + b'\x00' * (11 * 1024 * 1024)
    bnd = '----accbig'
    body = (f'--{bnd}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="big.png"\r\nContent-Type: image/png\r\n\r\n').encode() + big + \
           f'\r\n--{bnd}--\r\n'.encode()
    _throttle()
    rq = urllib.request.Request(BASE + '/api/images', data=body, method='POST',
                                headers={'Content-Type': f'multipart/form-data; boundary={bnd}',
                                         'X-Guest-Session': 'acc-err-big'})
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            st, j = r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        st = e.code
        try:
            j = json.loads(e.read().decode())
        except Exception:
            j = {}
    check('超过 10 MB → 413 / 41301',
          st == 413 and j.get('code') == 41301, f'http={st} code={j.get("code")}')


def sec_perf(n_samples: int, skip_bench: bool) -> dict:
    print(f'\n5. 性能验证（PRD 第 9 章端到端 ≤ 3000 ms，采样 {n_samples} 次）')
    uname = f'accperf{random.randint(100000, 999999)}'
    st, j, _h, _ = api('POST', '/api/auth/register',
                       {'username': uname, 'password': 'Passw0rd1'})
    if j.get('code') != 0:
        check('性能段注册账号', False, f'code={j.get("code")}')
        return {}
    T = {'Authorization': 'Bearer ' + j['data']['access_token']}
    uid = j['data']['user']['id']

    up_ms: list[float] = []
    up_srv: list[float] = []
    rec_wall: list[float] = []
    rec_srv: list[float] = []
    rec_infer: list[float] = []
    hits = 0
    imgs: list[str] = []
    samples = rotating_images(n_samples)

    for n, p in samples:
        st, up, hu, ms = upload(p, T)
        if up.get('code') != 0:
            continue
        iid = up['data']['image']['id']
        imgs.append(iid)
        up_ms.append(ms)
        with_srv = hu.get('x-process-time-ms')
        if with_srv:
            up_srv.append(float(with_srv))

        st, rc, hr, ms2 = api('POST', '/api/recognize', {'image_id': iid, 'top_k': 5}, T)
        if rc.get('code') != 0:
            continue
        d = rc['data']
        rec_wall.append(ms2)
        rec_srv.append(float(hr.get('x-process-time-ms') or 0))
        rec_infer.append(float(d['duration_ms']))
        hits += int(d['class_index'] == n - 1)

    check('采样成功样本数 = 期望', len(rec_wall) == len(samples),
          f'{len(rec_wall)}/{len(samples)}')
    check('采样识别命中率 ≥ 0.90', hits / max(1, len(rec_wall)) >= 0.90,
          f'{hits}/{len(rec_wall)}')

    S_up, S_up_srv = stat(up_ms), stat(up_srv)
    S_rec, S_rec_srv, S_inf = stat(rec_wall), stat(rec_srv), stat(rec_infer)

    # 端到端（客户端视角）= 上传 + 识别（用户点一次「识别」的完整可感知耗时）
    e2e = [a + b for a, b in zip(up_ms, rec_wall)] if len(up_ms) == len(rec_wall) else []
    S_e2e = stat(e2e)

    print(f'    · 上传      p50={S_up["p50"]:>7.1f}  p95={S_up["p95"]:>7.1f}  max={S_up["max"]:>7.1f} ms')
    print(f'    · 识别(端)  p50={S_rec["p50"]:>7.1f}  p95={S_rec["p95"]:>7.1f}  max={S_rec["max"]:>7.1f} ms')
    print(f'    · 识别(服)  p50={S_rec_srv["p50"]:>7.1f}  p95={S_rec_srv["p95"]:>7.1f}  max={S_rec_srv["max"]:>7.1f} ms')
    print(f'    · 预处理+推 p50={S_inf["p50"]:>7.1f}  p95={S_inf["p95"]:>7.1f}  max={S_inf["max"]:>7.1f} ms')
    print(f'    · 上传+识别 p50={S_e2e["p50"]:>7.1f}  p95={S_e2e["p95"]:>7.1f}  max={S_e2e["max"]:>7.1f} ms')

    check('识别（服务端）p50 ≤ 3000 ms', S_rec_srv['p50'] <= 3000, f"p50={S_rec_srv['p50']} ms")
    check('端到端（上传+识别）p50 ≤ 3000 ms', S_e2e['p50'] <= 3000, f"p50={S_e2e['p50']} ms")
    check('端到端 max ≤ 5000 ms', S_e2e['max'] <= 5000, f"max={S_e2e['max']} ms")

    bench = {}
    if not skip_bench:
        bench = stage_micro_bench(samples)
        if 'error' not in bench:
            print(f"    · 阶段微基准（{bench['device']}，n={bench['n']}）："
                  f"预处理 p50={bench['preprocess_ms']['p50']} ms / "
                  f"纯前向 p50={bench['forward_ms']['p50']} ms")
            check('预处理 p50 ≤ 200 ms（PRD §9 分解）',
                  bench['preprocess_ms']['p50'] <= 200,
                  f"p50={bench['preprocess_ms']['p50']} ms")
            check('纯推理 p50 ≤ 2000 ms（PRD §9 分解）',
                  bench['forward_ms']['p50'] <= 2000,
                  f"p50={bench['forward_ms']['p50']} ms")

    return {'user_id': uid, 'images': imgs, 'samples': len(rec_wall), 'hits': hits,
            'upload': S_up, 'upload_server': S_up_srv,
            'recognize_client': S_rec, 'recognize_server': S_rec_srv,
            'preprocess_plus_infer': S_inf, 'e2e': S_e2e, 'stage_bench': bench}


def login_admin() -> str | None:
    """尝试常见管理员口令（test_e2e.py 会把初始口令改为 Admin@9999 并持久化）。"""
    for pwd in ('Admin@9999', 'Admin@12345', 'Admin@2026'):
        st, j, _h, _ = api('POST', '/api/auth/login',
                           {'username': 'admin', 'password': pwd})
        if j.get('code') == 0:
            note(f'管理员口令命中：{pwd}')
            return 'Bearer ' + j['data']['access_token']
    note('管理员登录失败，跳过依赖管理权限的断言与善后')
    return None


def cleanup(admin_tok: str | None, user_ids: list[str],
            image_ids: list[str]) -> dict:
    """删除本轮创建的账号与图像。

    这是既有 probe_live_server.py 缺失的环节（它每跑一次留一个账号）。
    顺序有讲究：**先删账号、再删图像** —— 识别记录对图像是 CASCADE 外键，
    且记录删除端点是软删除（行仍在），图像删除端点会因此拒绝（42201）；
    而 DELETE /api/admin/users/{uid} 会物理删除该用户的识别记录并把
    image_asset.user_id 置 NULL，此后图像才满足「无识别记录」前提，
    可由管理员按 id 删除（管理员豁免归属校验）。
    """
    print('\n6. 善后（删除本轮创建的账号与图像）')
    if not admin_tok:
        check('善后：管理员令牌可用', False, '无法删除测试账号')
        return {'removed_users': 0, 'removed_images': 0}
    removed_u = removed_i = 0
    failed: list[str] = []
    for uid in user_ids:
        st, j, _h, _ = api('DELETE', f'/api/admin/users/{uid}', None, {'Authorization': admin_tok})
        if isinstance(j, dict) and j.get('code') == 0:
            removed_u += 1
        else:
            failed.append(f'user {uid}')
    for iid in image_ids:
        st, j, _h, _ = api('DELETE', f'/api/images/{iid}', None, {'Authorization': admin_tok})
        if isinstance(j, dict) and j.get('code') == 0:
            removed_i += 1
        else:
            failed.append(f'image {iid}')
    check('善后完成（测试账号与图像已清理）', not failed,
          f'删除账号 {removed_u} 个 / 图像 {removed_i} 张'
          + (f'；失败 {len(failed)} 项：{failed[:3]}' if failed else ''))
    return {'removed_users': removed_u, 'removed_images': removed_i,
            'failed': failed}


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description='M6 端到端联调与验收探针')
    ap.add_argument('--samples', type=int, default=25, help='性能采样次数（默认 25）')
    ap.add_argument('--skip-stage-bench', action='store_true', help='跳过阶段微基准')
    ap.add_argument('--no-cleanup', action='store_true', help='保留测试账号与图像')
    args = ap.parse_args()

    print('=' * 78)
    print('  M6 · 端到端联调与验收')
    print(f'  后端 = {BASE}')
    print(f'  前端 = {FRONTEND}')
    print('=' * 78)

    report: dict = {'started_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'base': BASE, 'frontend': FRONTEND, 'samples': args.samples}

    topo = sec_topology()
    if not topo:
        print('\n  \u2717 后端不可达，终止。')
        return 2
    report['topology'] = topo

    admin_tok = login_admin()
    report['admin_login'] = bool(admin_tok)

    guest = sec_guest()
    report['guest'] = {k: v for k, v in guest.items() if k != 'recognize_sample'}
    if guest.get('recognize_sample'):
        s = guest['recognize_sample']
        report['guest']['sample'] = {
            'class_index': s['class_index'], 'cn_name': s['cn_name'],
            'confidence': s['confidence'], 'duration_ms': s['duration_ms'],
            'model_version': s['model_version'],
            'top5': [{'rank': c['rank'], 'cn_name': c['cn_name'],
                      'confidence': c['confidence']} for c in s['candidates']],
        }

    user = sec_user(admin_tok)
    report['user'] = user

    sec_errors(admin_tok)

    perf = sec_perf(args.samples, args.skip_stage_bench)
    report['perf'] = perf

    created_users: list[str] = []
    created_images: list[str] = []
    if user.get('user_id'):
        created_users.append(user['user_id'])
    created_images += user.get('images') or []
    if perf.get('user_id'):
        created_users.append(perf['user_id'])
    created_images += perf.get('images') or []
    if guest.get('image_id'):
        created_images.append(guest['image_id'])

    if args.no_cleanup:
        note('按 --no-cleanup 保留测试数据')
        report['cleanup'] = {'skipped': True}
    else:
        report['cleanup'] = cleanup(admin_tok, created_users, created_images)

    report['finished_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
    report['passed'] = PASS['n']
    report['failed'] = len(FAILS)
    report['failures'] = FAILS
    report['notes'] = NOTES

    out = ROOT / 'backend' / 'logs' / 'acceptance_report.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')

    print()
    print('=' * 78)
    print(f'  合计  通过 {PASS["n"]} / 失败 {len(FAILS)}')
    for f in FAILS:
        print(f'    \u2717 {f}')
    if NOTES:
        print('  说明：')
        for n in NOTES:
            print(f'    \u2013 {n}')
    print(f'  报告  {out}')
    print('=' * 78)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
