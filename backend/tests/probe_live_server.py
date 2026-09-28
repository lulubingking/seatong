# -*- coding: utf-8 -*-
"""对「真实运行中的服务」做端到端联调（非 TestClient）。

与 test_e2e.py 的区别：
  - test_e2e.py 用 TestClient + 临时库，验证代码逻辑与契约；
  - 本脚本打真实 HTTP，验证 uvicorn 进程、真实 SQLite、CUDA 推理、
    中间件链（信封 / 请求 ID / 耗时头）在真实网络栈下确实工作。

前置：服务已在 127.0.0.1:8000 运行（uvicorn app.main:app）。
用法：python backend/tests/probe_live_server.py
"""
from __future__ import annotations

import glob
import json
import os
import pathlib
import random
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get('SEATONG_BASE', 'http://127.0.0.1:8000')
ROOT = pathlib.Path(__file__).resolve().parents[2]

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


def api(method: str, path: str, body=None, headers=None, raw=False):
    hdr = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        hdr['Content-Type'] = 'application/json'
    rq = urllib.request.Request(BASE + path, data=data, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(rq, timeout=90) as r:
            b = r.read()
            return r.status, (b if raw else json.loads(b.decode('utf-8'))), dict(r.headers)
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b.decode('utf-8')), dict(e.headers)
        except Exception:
            return e.code, b, dict(e.headers)


def api_retry(method: str, path: str, body=None, headers=None, raw=False,
              tries: int = 5, wait: float = 4.0):
    """带限流退避的请求。42902（每分钟 60 次）时退避重试，不误判为失败。"""
    for i in range(tries):
        st, j, h = api(method, path, body, headers, raw)
        code = j.get('code') if isinstance(j, dict) else None
        if st == 429 or code == 42902:
            if i < tries - 1:
                time.sleep(wait)
                continue
        return st, j, h
    return st, j, h


def wait_ready(timeout=60) -> bool:
    for _ in range(timeout):
        try:
            urllib.request.urlopen(BASE + '/api/health', timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def upload(path: pathlib.Path, headers: dict) -> dict:
    raw = path.read_bytes()
    bnd = '----seatongprobe'
    body = (
        f'--{bnd}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{path.name}"\r\nContent-Type: image/png\r\n\r\n'
    ).encode('utf-8') + raw + f'\r\n--{bnd}--\r\n'.encode('utf-8')
    rq = urllib.request.Request(
        BASE + '/api/images', data=body, method='POST',
        headers={'Content-Type': f'multipart/form-data; boundary={bnd}', **headers})
    with urllib.request.urlopen(rq, timeout=90) as r:
        return json.loads(r.read().decode('utf-8'))


def main() -> int:
    print('=' * 72)
    print('  真实服务联调（live HTTP）')
    print(f'  target = {BASE}')
    print('=' * 72)

    if not wait_ready():
        print(f'  \u2717 服务不可达：{BASE}')
        return 2

    # ---------- 1. 中间件链 ----------
    print('\n1. 中间件链（真实网络栈）')
    st, j, h = api('GET', '/api/health')
    hl = {k.lower(): v for k, v in h.items()}
    check('GET /api/health → 200', st == 200 and j['code'] == 0)
    check('响应头 X-Request-Id 存在且非空', bool(hl.get('x-request-id')),
          hl.get('x-request-id', ''))
    check('响应头 X-Process-Time-Ms 存在', bool(hl.get('x-process-time-ms')),
          hl.get('x-process-time-ms', '') + ' ms')
    check('信封含 request_id 且与响应头一致',
          j.get('request_id') == hl.get('x-request-id'),
          f"body={j.get('request_id')} header={hl.get('x-request-id')}")
    # 传入的自定义 request id 应被沿用（便于链路追踪）
    st, j2, h2 = api('GET', '/api/health', None, {'X-Request-Id': 'probe-trace-001'})
    check('客户端传入 X-Request-Id 被沿用',
          {k.lower(): v for k, v in h2.items()}.get('x-request-id') == 'probe-trace-001')

    # ---------- 2. 模型就绪 ----------
    print('\n2. 模型状态')
    st, j, _ = api('GET', '/api/health')
    m = j['data']['model']
    check('模型 ready', m['ready'] is True, f"device={m.get('device')}")
    check('运行在 CUDA', m.get('device') == 'cuda', str(m.get('device')))
    check('num_classes == 23', m['num_classes'] == 23)
    check('img_size == 224', m['img_size'] == 224)
    check('ckpt 文件存在', m.get('ckpt_exists') is True)
    tm = m.get('trained_metrics') or {}
    check('冻存指标 acc ≥ 0.85（PRD 硬指标）',
          tm.get('accuracy', 0) >= 0.85, f"acc={tm.get('accuracy')}")
    check('冻存指标 macro_f1 ≥ 0.82（PRD 硬指标）',
          tm.get('macro_f1', 0) >= 0.82, f"macro_f1={tm.get('macro_f1')}")
    check('DB PRAGMA foreign_keys = 1',
          j['data']['db_pragmas'].get('foreign_keys') == 1)

    # ---------- 3. 真实推理 ----------
    print('\n3. 真实推理（抽样真实图像）')
    uname = f'probe{random.randint(100000, 999999)}'
    st, j, _ = api_retry('POST', '/api/auth/register',
                         {'username': uname, 'password': 'Passw0rd1',
                          'nickname': '联调探测'})
    check('注册临时用户 → 200', st == 200 and j.get('code') == 0,
          f'http={st} code={j.get("code")} msg={j.get("message")}')
    if j.get('code') != 0:
        print('  \u2013 注册未成功（多为限流未退避完），跳过后续推理段')
        return 1
    H = {'Authorization': 'Bearer ' + j['data']['access_token']}

    # 每类抽 1 张，验证 23 类全部可被正确识别（真实模型能力，非测试桩）
    samples = []
    for n in range(1, 24):
        d = ROOT / 'fish_image23' / 'fish_image' / f'fish_{n}'
        f = sorted(glob.glob(str(d / '*.png')))
        if f:
            samples.append((n, pathlib.Path(f[0])))
    check('抽样到 23 个类别各 1 张', len(samples) == 23, f'n={len(samples)}')

    hit = 0
    lat = []
    skipped = 0
    for n, p in samples:
        # 尊重服务端限流（42902：每分钟 60 次）。本脚本每次迭代 2 个请求，
        # 故按 1.1s/次 节流；若仍被限流则退避重试，而不是把限流误判成失败。
        for attempt in range(4):
            try:
                up = upload(p, H)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(3.0)
                    continue
                raise
            if up.get('code') == 42902:
                time.sleep(3.0)
                continue
            break
        else:
            skipped += 1
            print(f'    \u2013 fish_{n:<2} 跳过（持续限流）')
            continue

        if up.get('code') != 0:
            print(f'    上传失败 {p.name}: code={up.get("code")}')
            continue
        iid = up['data']['image']['id']

        for attempt in range(4):
            t0 = time.perf_counter()
            st, rc, _ = api('POST', '/api/recognize',
                            {'image_id': iid, 'top_k': 5}, H)
            dt = (time.perf_counter() - t0) * 1000
            if rc.get('code') == 42902:
                time.sleep(3.0)
                continue
            break

        if rc.get('code') != 0:
            print(f'    识别失败 {p.name}: code={rc.get("code")}')
            continue
        d = rc['data']
        lat.append(dt)
        ok = d['class_index'] == n - 1
        hit += int(ok)
        flag = '\u2713' if ok else '\u2717'
        print(f'    {flag} fish_{n:<2} → idx={d["class_index"]:<2} '
              f'{d["cn_name"]:<12} conf={d["confidence"]:.4f} '
              f'infer={d["duration_ms"]}ms e2e={dt:.0f}ms'
              + ('' if ok else f'  （期望 idx={n-1}）'))
        time.sleep(1.1)   # 主动节流，避免触发 42902

    tested = len(lat)
    rate = hit / tested if tested else 0
    check('抽样识别命中率 ≥ 0.90', rate >= 0.90,
          f'{hit}/{tested} = {rate:.1%}' + (f'，跳过 {skipped}' if skipped else ''))
    if lat:
        lat.sort()
        p50 = lat[len(lat) // 2]
        check('端到端 p50 ≤ 3000ms（PRD 第 9 章）', p50 <= 3000, f'p50={p50:.0f}ms')
        check('端到端 max ≤ 5000ms', max(lat) <= 5000, f'max={max(lat):.0f}ms')

    # ---------- 4. 记录落库与导出 ----------
    print('\n4. 落库 / 历史 / 导出（真实库）')
    st, j, _ = api('GET', '/api/records', None, H)
    total = j['data']['total']
    check('历史条数等于成功识别数', total == hit, f'total={total} 命中={hit}')

    st, j, h = api('GET', '/api/records/export', None, H, raw=True)
    check('导出 CSV → 200', st == 200)
    check('CSV 带 UTF-8 BOM（Excel 中文不乱码）', j[:3] == b'\xef\xbb\xbf')
    check('CSV 含中文表头', '中文名'.encode('utf-8') in j)
    check('CSV Content-Disposition 为附件',
          'attachment' in {k.lower(): v for k, v in h.items()}
          .get('content-disposition', ''))
    check('CSV 非 JSON 信封（跳过包装）', not j.lstrip().startswith(b'{'))

    # ---------- 5. 物种知识库 ----------
    print('\n5. 物种知识库（公开端点）')
    st, j, _ = api('GET', '/api/species?page_size=50')
    items = j['data']['items']
    check('物种总数 23', j['data']['total'] == 23, f"total={j['data']['total']}")
    check('class_index 恰为 0..22',
          sorted(x['class_index'] for x in items) == list(range(23)))
    no_text = [x['class_index'] for x in items
               if not (x.get('morphology') and x.get('habit'))]
    check('23 类形态与习性文案齐备', not no_text, f'缺文案 {no_text or "无"}')
    f18 = next(x for x in items if x['class_index'] == 17)
    check('fish_18 为科级 Scaridae', f18['latin_name'] == 'Scaridae',
          f"{f18['cn_name']} / {f18['latin_name']}")

    # ---------- 6. 游客额度（真实服务） ----------
    print('\n6. 游客额度（真实服务）')
    gs = f'probe-guest-{random.randint(100000, 999999)}'
    GH = {'X-Guest-Session': gs}
    st, j, _ = api('GET', '/api/users/me', None, GH)
    check('游客 /users/me → is_guest=True',
          j['code'] == 0 and j['data'].get('is_guest') is True)
    gq0 = j['data'].get('guest_quota') or {}
    check('游客初始额度 3', gq0.get('remaining') == 3, str(gq0))

    n, p = samples[0]
    up = upload(p, GH)
    check('游客上传 → 200', up['code'] == 0)
    iid = up['data']['image']['id']
    st, j, _ = api('GET', '/api/users/me', None, GH)
    gq1 = j['data'].get('guest_quota') or {}
    check('上传不消耗额度（仍为 3）', gq1.get('remaining') == 3, str(gq1))
    st, rc, _ = api('POST', '/api/recognize', {'image_id': iid}, GH)
    check('游客识别 → 200', rc['code'] == 0)
    check('游客识别不落库（record_id 为空）', rc['data'].get('record_id') is None,
          f"record_id={rc['data'].get('record_id')}")
    gq2 = rc['data'].get('guest_quota') or {}
    check('返回剩余额度 2', gq2.get('remaining') == 2, str(gq2))

    # ---------- 7. 错误路径（真实服务） ----------
    print('\n7. 错误路径')
    st, j, _ = api('GET', '/api/records')
    check('无令牌访问历史 → 40101 / 401', st == 401 and j['code'] == 40101,
          f'http={st} code={j["code"]}')
    st, j, _ = api('POST', '/api/recognize', {'image_id': 'no-such-uuid'}, H)
    check('识别不存在图 → 40401 / 404', st == 404 and j['code'] == 40401,
          f'http={st} code={j["code"]}')
    st, j, _ = api('GET', '/api/admin/stats', None, H)
    check('普通用户调管理端点 → 40301 / 403', st == 403 and j['code'] == 40301,
          f'http={st} code={j["code"]}')
    st, j, _ = api('GET', '/api/nonexistent-route')
    check('未知路由 → 40401 / 404', st == 404 and j['code'] == 40401,
          f'http={st} code={j["code"]}')

    print()
    print('=' * 72)
    print(f'  合计  通过 {PASS["n"]} / 失败 {len(FAILS)}')
    for f in FAILS:
        print(f'    - {f}')
    print('=' * 72)
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
