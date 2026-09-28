# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · API 契约与实现一致性校验器

用途：把「文档声明的端点」与「后端实际注册的端点」做集合级比对。
     这是 D8 V1.1 校准工作的固化 —— 避免文档与实现再次静默漂移。

校验五组断言：
  A. D8 第 11.2 节的端点全量清单  == 后端 openapi 实际端点（双向零差集）
  B. PRD 第 8.1 节的端点清单      ⊂ 后端实际端点（PRD 是子集，允许实现多出）
  C. 前端 src/api/index.ts 的 ENDPOINTS 常量表 ⊆ 后端实际端点
  D. 已下线的旧路径 ∉ 后端实际端点（防命名回退）
  E. D8 第 11.1 节追溯的 FR 编号 ∈ PRD 第 4 章定义的 FR 编号（防悬空引用）

用法（须先启动后端）：
    python tools/api_contract_verify.py [base_url]

退出码：0 全绿 / 1 有失败
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0
FAILS = []


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


def norm(ep: str) -> str:
    """把路径参数统一成 {}，使 /a/{x} 与 /a/{y} 视为同一端点。"""
    return re.sub(r'\{[^}]+\}', '{}', ep)


def read(path: str) -> str:
    """读文本文件，不存在则返回空串（断言会以空集形式报错，便于定位）。"""
    if not os.path.exists(path):
        return ''
    with open(path, encoding='utf-8') as f:
        return f.read()


def fetch_backend_endpoints() -> set:
    """取后端实际注册的端点。

    【坑】不能用 app.routes 直接读 —— FastAPI 的 include_router 会生成
    _IncludedRouter 包装对象，不扁平化进 app.routes。必须走 openapi()。
    【坑】EnvelopeMiddleware 会包裹 openapi.json，故路径在 d['data']['paths']。
    """
    try:
        with urllib.request.urlopen(f'{BASE}/openapi.json', timeout=30) as r:
            raw = json.loads(r.read())
    except urllib.error.URLError as e:
        print(f'\n✗ 无法连接后端 {BASE}：{e}\n  请先启动后端。\n')
        sys.exit(2)

    # 兼容有无信封两种情况
    paths = raw.get('data', raw).get('paths', {})
    eps = set()
    for p, methods in paths.items():
        for m in methods:
            if m.lower() in ('get', 'post', 'put', 'patch', 'delete'):
                eps.add(norm(f'{m.upper()} {p}'))
    return eps


def extract_md_endpoints(path: str, section: str, stop_at: str) -> set:
    """从 Markdown 的某章节里抽取端点。支持两种表格布局：

    D8 §11.2 形式（带序号列）：
        | 12 | GET | `/api/xxx` | ...            （表格行）
        | 12 | ★ GET | `/api/xxx` | ...          （带 ★ 新增标记）
        | ☆ | GET | `/api/xxx` | ...             （别名行）

    PRD §8.1 形式（无序号列，四列）：
        | GET | `/api/xxx` | 用途 | 权限 | 需求 |
    """
    with open(path, encoding='utf-8') as f:
        txt = f.read()
    if section not in txt:
        return set()
    seg = txt[txt.index(section):]
    if stop_at and stop_at in seg:
        seg = seg[:seg.index(stop_at)]

    out = set()
    # 布局 1：序号列（数字或 ☆）
    pat1 = re.compile(
        r'^\|\s*(?:\d+|☆)\s*\|\s*(?:★\s*)?(?:☆\s*)?'
        r'(GET|POST|PUT|PATCH|DELETE)\s*\|'
        r'\s*`([^`]+)`\s*\|', re.M)
    # 布局 2：无序号列，方法直接在第一列
    pat2 = re.compile(
        r'^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|'
        r'\s*`([^`]+)`\s*\|', re.M)
    for pat in (pat1, pat2):
        for m in pat.finditer(seg):
            out.add(norm(f'{m.group(1)} {m.group(2)}'))
    return out


def extract_ts_paths(path: str) -> set:
    """从前端 ENDPOINTS 常量表抽取**纯路径**（不含方法）。

    匹配形如：  records: '/api/records',
                recordById: (id: string) => `/api/records/${id}`,

    【为何只取路径】前端 `ENDPOINTS` 是纯路径常量表，不含 HTTP 方法 ——
    方法由调用点（`http.get` / `http.delete` 等）决定。故只能用路径做
    子集校验：前端引用的每个路径，后端至少要有一个方法能响应它。
    """
    if not os.path.exists(path):
        return set()
    with open(path, encoding='utf-8') as f:
        txt = f.read()

    out = set()
    for m in re.finditer(r":\s*'(/api/[^']+)'", txt):
        out.add(m.group(1))
    for m in re.finditer(r":\s*(?:\([^)]*\)\s*=>\s*)?`(/api/[^`]+)`", txt):
        p = re.sub(r'\$\{[^}]+\}', '{x}', m.group(1))
        out.add(p)
    return out


def main():
    print('=' * 74)
    print(f'  API 契约与实现一致性校验   base={BASE}')
    print('=' * 74)

    D8 = os.path.join(ROOT, 'docs', '海瞳鱼鉴-API接口契约.md')
    PRD = os.path.join(ROOT, 'docs', '海瞳鱼鉴-PRD.md')
    TS = os.path.join(ROOT, 'frontend', 'src', 'api', 'index.ts')

    print('\n读取后端实际端点 ...')
    be = fetch_backend_endpoints()
    be_norm = {norm(x) for x in be}
    print(f'  后端注册 {len(be_norm)} 条端点')

    # ---------- A. D8 §11.2 全量清单 ----------
    print(f'\nA. D8 §11.2 端点全量清单 vs 后端')
    d8 = extract_md_endpoints(D8, '### 11.2', '### 11.3')
    check('能解析出 D8 端点清单', len(d8) > 0, f'n={len(d8)}')
    only_d8 = sorted(d8 - be_norm)
    only_be = sorted(be_norm - d8)
    check('D8 声明的端点后端全部存在', not only_d8,
          f'缺失 {len(only_d8)} 条：{only_d8}' if only_d8 else f'n={len(d8)}')
    check('后端端点 D8 全部收录', not only_be,
          f'未收录 {len(only_be)} 条：{only_be}' if only_be else '双向零差集')
    if not only_d8 and not only_be:
        check('D8 与后端端点集合完全相等', True, f'{len(d8)} 条')

    # ---------- B. PRD §8.1 原始 27 条 ----------
    print(f'\nB. PRD §8.1 原始端点 vs 后端')
    prd = extract_md_endpoints(PRD, '### 8.1', '### 8.2')
    prd_extra = sorted(prd - be_norm)
    check('能解析出 PRD 端点清单', len(prd) > 0, f'n={len(prd)}')
    check('PRD 声明的端点后端全部存在（无遗漏）', not prd_extra,
          f'PRD 有后端无 {len(prd_extra)} 条：{prd_extra}' if prd_extra
          else f'PRD {len(prd)} 条均在实现中')
    # 实现多出的是允许的，但要报告
    be_minus_prd = sorted(be_norm - prd)
    print(f'  · 实现相对 PRD 多出 {len(be_minus_prd)} 条（PRD 待同步，见 D8 EC-11）')
    for x in be_minus_prd:
        print(f'      {x}')

    # ---------- C. 前端 api 层 ----------
    print(f'\nC. 前端 ENDPOINTS 常量表 vs 后端')
    ts = extract_ts_paths(TS)
    check('能解析出前端端点', len(ts) > 0, f'n={len(ts)}')
    # 前端的 key 是纯路径，后端是「方法 + 路径」，故取后端的路径集合作子集比对
    be_paths = {norm(x.split(' ', 1)[1]) for x in be_norm}
    ts_bad = sorted(p for p in ts if norm(p) not in be_paths)
    check('前端引用的每条路径后端均可达（无死端点）', not ts_bad,
          f'死端点 {len(ts_bad)} 条：{ts_bad}' if ts_bad
          else f'{len(ts)} 条路径全部可达')

    # ---------- D. 旧路径下线守护 ----------
    print(f'\nD. 已下线旧路径不得复活')
    RETIRED = [
        'GET /api/users',
        'PATCH /api/admin/config/{}',
        'PUT /api/admin/config/{}',
        'POST /api/users/{}/password',
        'PATCH /api/users/{}/password',
        'GET /api/admin/logs/{}',
    ]
    for ep in RETIRED:
        check(f'{ep} 已下线', norm(ep) not in be_norm)

    # ---------- E. FR 追溯有效性 ----------
    # 背景：D8 §11.1 把每条端点追溯到一条 FR。曾出现 GET /api/admin/stats
    #       追溯到 FR-USER-10，而 PRD 第 4 章的 FR-USER 只到 09 —— 编号悬空。
    #       本组断言即为此类缺陷的守护。
    print(f'\nE. D8 §11.1 追溯的 FR 编号 vs PRD §4 定义')
    prd_txt = read(PRD)
    d8_txt = read(D8)
    # PRD 第 4 章功能清单：形如 `| FR-USER-01 | ...`（模块名不含 PERF/SEC 等 NFR 类）
    prd_fr = set(re.findall(
        r'^\|\s*(FR-(?!PERF|SEC|REL|COMPAT|MAINT)[A-Z]+-\d+)\s*\|', prd_txt, re.M))
    # D8 §11.1 追溯表：形如 `| 29 | ★ POST | \`/api/...\` | ... | FR-USER-07（派生） | 9.2 |`
    seg111 = d8_txt[d8_txt.find('### 11.1'):d8_txt.find('### 11.2')]
    d8_refs = set(re.findall(r'\b(FR-(?!PERF|SEC|REL|COMPAT|MAINT)[A-Z]+-\d+)\b', seg111))
    check('能解析出 PRD 的 FR 编号', len(prd_fr) > 0, f'n={len(prd_fr)}')
    check('能解析出 D8 §11.1 的 FR 追溯', len(d8_refs) > 0, f'n={len(d8_refs)}')
    dangling = sorted(d8_refs - prd_fr)
    check('D8 追溯的 FR 编号均在 PRD 中有定义（无悬空引用）', not dangling,
          f'悬空引用：{dangling}' if dangling else f'{len(d8_refs)} 个编号全部有效')

    # ---------- 汇总 ----------
    print()
    print('=' * 74)
    print(f'  合计  通过 {PASS} / 失败 {FAIL}')
    if FAILS:
        print('  失败项：')
        for f in FAILS:
            print(f'    - {f}')
    print('=' * 74)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
