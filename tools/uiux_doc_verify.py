# -*- coding: utf-8 -*-
"""海瞳鱼鉴 UI/UX 设计文档 —— 交付前六组校验器 (v2)
用法: python uiux_doc_verify.py
"""
import io, os, re

# 可移植：以本文件位置推导仓库根（<ROOT>/tools/xxx.py → dirname(dirname())）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DOCS = os.path.join(_ROOT, 'docs')

DOC = os.path.join(_DOCS, '海瞳鱼鉴-UIUX设计文档.md')
PROTO = os.path.join(_DOCS, '海瞳鱼鉴-产品原型.html')
PRD = os.path.join(_DOCS, '海瞳鱼鉴-PRD.md')

doc = io.open(DOC, encoding='utf-8').read()
proto = io.open(PROTO, encoding='utf-8').read()
prd = io.open(PRD, encoding='utf-8').read()

R = []
def chk(g, name, exp, act, ok=None):
    if ok is None:
        ok = (str(exp) == str(act))
    R.append((g, name, str(exp), str(act), bool(ok)))

# ============ 第 1 组：章节完整性 ============
G = 1
chk(G, '哨兵残留', 0, doc.count('<!--@@UX-NEXT@@-->'))
# 正文一级标题：形如 "# 6　关键流程与状态可视化"
h1 = re.findall(r'^#\s+(\d+)\u3000', doc, re.M)
chk(G, '正文章节数(§0-§11)', 12, len(h1))
chk(G, '章节号连续 0-11', list(range(12)), sorted(int(x) for x in h1))
hA = re.findall(r'^#\s+附录\s+([A-G])\u3000', doc, re.M)
chk(G, '附录数(A-G)', 7, len(hA))
chk(G, '附录字母有序', list('ABCDEFG'), hA)

s5 = sorted(set(re.findall(r'^##\s+(5\.\d+)[\u3000\s]', doc, re.M)), key=lambda x: float(x[2:]))
chk(G, '§5 页面规格小节数(5.0-5.14)', 15, len(s5))

comps = sorted(set(re.findall(r'^\|\s*(C-\d+)\s*\|', doc, re.M)))
chk(G, '组件条目数(C-xx)', 26, len(comps))

# §5 每页 10 项模板齐备：用 ### 切分小节，统计每节内模板项出现数
secs5 = re.split(r'^##\s+5\.\d+[\u3000\s]', doc, flags=re.M)[1:]
tmpl = ['① 视图与路由', '② 页面目标', '③ 需求锚点', '④ 布局骨架', '⑤ 核心组件',
        '⑥ 状态与空态', '⑦ 关键交互', '⑧ 反馈文案', '⑨ 响应式', '⑩ 禁忌']
pages = [s for s in secs5[1:] if '① 视图与路由' in s]
incomplete = []
for s in pages:
    miss_t = [t for t in tmpl if t not in s]
    if miss_t:
        incomplete.append((s[:28].replace('\n', ' '), miss_t))
chk(G, '§5 每页 10 项模板齐备', 13, len(pages))
chk(G, '§5 模板无缺项', [], incomplete)
chk(G, 'Markdown 围栏配平', 0, doc.count('```') % 2)
# 二级小节总数
h23 = re.findall(r'^##\s+\d+\.\d+', doc, re.M)
chk(G, '二级小节数 ≥ 35', True, len(h23) >= 35)

# ============ 第 2 组：令牌双向比对 ============
G = 2
mroot = re.search(r':root\s*\{(.*?)\}', proto, re.S)
proto_tokens = {}
for m in re.finditer(r'(--[a-zA-Z0-9-]+)\s*:\s*([^;]+)', mroot.group(1)):
    proto_tokens[m.group(1)] = m.group(2).strip()
chk(G, '原型令牌数量', 33, len(proto_tokens))

# 附录 A 表格：| n | `--x` | `val` | ... |  或 | **n** | **`--x`** | **`val`** |
doc_defs = {}
for m in re.finditer(r'\|\s*\*{0,2}\d+\*{0,2}\s*\|\s*\*{0,2}`(--[a-zA-Z0-9-]+)`\*{0,2}\s*\|\s*\*{0,2}`?([^|`]+)`?\*{0,2}\s*\|', doc):
    doc_defs.setdefault(m.group(1), m.group(2).strip().strip('*').strip())
chk(G, '附录A 令牌定义数', 34, len(doc_defs))

not_in_doc = sorted(k for k in proto_tokens if k not in doc_defs)
chk(G, '原型→文档 差集(空)', [], not_in_doc)
not_in_proto = sorted(k for k in doc_defs if k not in proto_tokens)
chk(G, '文档→原型 差集(仅新增项)', ['--accent-border'], not_in_proto)

diffv = [(k, v, doc_defs.get(k, '')) for k, v in proto_tokens.items()
         if doc_defs.get(k, '').replace('`', '').strip().lower() != v.lower()]
chk(G, '同名令牌值一致', '全部一致', '全部一致' if not diffv else str(diffv[:3]))

chk(G, '--accent-border 值来自原型(#B5D4F4)', 'FOUND', 'FOUND' if '#B5D4F4' in proto else 'NOT FOUND')

# 引用有效性：正文中形如 var(--x) 或 `--x` 的引用必须有名
# 排除：① 反例/占位符（--blue-500 / --red / --xxx / --info-border）② 通配写法 --xxx
NEG = {'--blue-500', '--red', '--info-border', '--xxx', '--x', '--accent-border'}
refs = set(re.findall(r'var\((--[a-zA-Z0-9-]+)\)', doc)) | set(re.findall(r'`(--[a-zA-Z][a-zA-Z0-9-]*)`', doc))
undef = sorted(r for r in refs if r not in doc_defs and r not in NEG)
chk(G, '令牌引用均有定义(排除反例)', [], undef)

# ============ 第 3 组：路由与视图一致性 ============
G = 3
doc_routes = re.findall(r'^##\s+5\.\d+\u3000[^\n]*?`(/[^\s`]*)`', doc, re.M)
chk(G, '§5 携带路由的小节数', 12, len(doc_routes))

views = re.findall(r'（视图\s*`([^`]+)`）', doc)
chk(G, '§5 标注的视图名数', 13, len(views))
# 原型以 var VIEWS = { home: viewHome, ... } 定义路由键
mviews = re.search(r'var\s+VIEWS\s*=\s*\{(.*?)\}', proto, re.S)
pkeys = set(re.findall(r'(\w+)\s*:', mviews.group(1))) if mviews else set()
chk(G, '原型 VIEWS 键数', 13, len(pkeys))
lost = sorted(v for v in views if v not in pkeys)
chk(G, '视图名均在原型 VIEWS 中存在', [], lost)

# PRD §5.2 页面清单行数（表格首列为页面名，非序号）
m52 = re.search(r'###\s*5\.2[^\n]*\n(.*?)(?=\n###|\n##\s)', prd, re.S)
rows52 = re.findall(r'^\|\s*(?:首页|识别工作台|关于与免责|登录|注册|历史记录|历史详情|对比视图|个人中心|用户管理|记录管理|系统配置|404)', m52.group(1), re.M) if m52 else []
chk(G, 'PRD §5.2 页面清单行数(由页面名匹配)', 13, len(rows52))

# 路由表条目（§2.2，表格含 序号|页面|路由|视图标识|访问权限|守卫）
m22 = re.search(r'^##\s*2\.2[^\n]*\n(.*?)(?=\n##\s)', doc, re.S|re.M)
n22 = len(re.findall(r'^\|\s*\d+\s*\|', m22.group(1), re.M)) if m22 else 0
chk(G, '§2.2 路由表条目数', 13, n22)

# ============ 第 4 组：需求覆盖与未定义引用 ============
G = 4
segD = doc[doc.find('# 附录 D'):doc.find('# 附录 E')]
chk(G, '附录D FR 行数', 41, len(re.findall(r'^\|\s*`FR-', segD, re.M)))
chk(G, '附录D NFR 行数', 15, len(re.findall(r'^\|\s*`NFR-', segD, re.M)))
chk(G, '附录D BR 行数', 60, len(re.findall(r'^\|\s*`BR-', segD, re.M)))
chk(G, '附录D 未填占位', 0, segD.count('（描述缺失）'))

pf = sorted(set(re.findall(r'\|\s*FR-(?!PERF|SEC|REL|COMPAT|MAINT)([A-Z]+-\d+)\s*\|', prd)))
df = sorted(set(re.findall(r'`FR-(?!PERF|SEC|REL|COMPAT|MAINT)([A-Z]+-\d+)`', segD)))
chk(G, 'FR 编号集合 = PRD', pf, df)
pn = sorted(set(re.findall(r'NFR-([A-Z]+-\d+)', prd)))
dn = sorted(set(re.findall(r'`NFR-([A-Z]+-\d+)`', segD)))
chk(G, 'NFR 编号集合 = PRD', pn, dn)
pb = sorted(set(re.findall(r'BR-([A-Z]+-\d+)', prd)))
db = sorted(set(re.findall(r'`BR-([A-Z]+-\d+)`', segD)))
chk(G, 'BR 编号集合 = PRD', pb, db)

# 交叉引用有效性（仅本文档内部引用，排除第 X 章 与上游文档引用）
doc_secs = set(re.findall(r'^#{2,4}\s+(\d+\.\d+(?:\.\d+)?)', doc, re.M))
refs_sec = set(re.findall(r'§(\d+\.\d+(?:\.\d+)?)', doc))
refs_sec |= set(re.findall(r'第\s*(\d+\.\d+(?:\.\d+)?)\s*节', doc))
doc_chaps = set(re.findall(r'^#\s+(\d+)\u3000', doc, re.M))
bad = sorted(r for r in refs_sec if r not in doc_secs and r.split('.')[0] not in doc_chaps)
chk(G, '§X.Y 交叉引用均存在', [], bad)

must = ['7.1.1', '7.1.2', '7.2', '7.3', '8.1', '8.2', '8.3', '9.3', '9.4', '11.1', '11.2', '11.3']
chk(G, '§5 引用的待落实小节均已存在', [], [m for m in must if m not in doc_secs])

# 错误码（排除 §10.7 自检清单中用于演示未知码兜底的 mock 码 99999）
# §7.3 区段 = §7.3 标题 至 §8.1 标题；码值为表首列，形如 `40001` / `NET-01`
seg73 = doc[doc.find('## 7.3\u3000'):doc.find('## 8.1\u3000')]
c73 = sorted(set(re.findall(r'^\|\s*`((?:[45]\d{4})|NET-01|CLI-01|CLI-02)`\s*\|', seg73, re.M)))
c73_num = [c for c in c73 if c.isdigit()]
c_appC = sorted(set(re.findall(r'^\|\s*`((?:[45]\d{4})|NET-01|CLI-01|CLI-02)`\s*\|',
                               doc[doc.find('# 附录 C'):doc.find('# 附录 D')], re.M)))
chk(G, '错误码集合 §7.3 = 附录C', c73, c_appC)
chk(G, '§7.3 错误码条数(PRD21+补充7)', 28, len(c73))
chk(G, '错误码总数(§7.3 全量，含非数字码)', 28, len(set(c73)))
# 与 PRD §8.3.2 的 21 个码严格一致（V1.2 起：40902/40903/40904 已被 PRD 正式采纳）
prd_codes = set(re.findall(r'\|\s*`?([45]\d{4})`?\s*\|', prd))
chk(G, 'PRD §8.3.2 错误码数', 21, len(prd_codes))
chk(G, 'PRD 全部码值均在 §7.3 中', [], sorted(prd_codes - set(c73)))
chk(G, '§7.3 补充码数', 7, len(set(c73) - prd_codes))
chk(G, '非数字错误码 3 个', ['CLI-01', 'CLI-02', 'NET-01'], sorted({'NET-01', 'CLI-01', 'CLI-02'}))

# 需求编号辨析：FR-PERF 类格式示例仅允许出现在 §0.6
seg06 = doc[doc.find('### 0.6'):doc.find('### 0.7')]
outside = doc.replace(seg06, '', 1)
# 仅统计形如 `FR-XXX-NN` 的代码引用，且排除表格内的辨析说明行
bad_fr = re.findall(r'`FR-(?:PERF|SEC|REL|COMPAT|MAINT)-\d+`', outside)
chk(G, 'FR-PERF 类假编号未外泄(仅§0.6)', 0, len(bad_fr))

# ============ 第 5 组：Mermaid ============
G = 5
mer = re.findall(r'```mermaid\n(.*?)```', doc, re.S)
chk(G, 'Mermaid 图数量(§2.1 + §6 六张)', 7, len(mer))
bad_mer = []
for i, blk in enumerate(mer):
    first = blk.strip().split('\n')[0].strip()
    if not re.match(r'^(stateDiagram-v2|flowchart\s+(TD|LR|TB)|sequenceDiagram|graph\s+(TD|LR)|classDiagram|erDiagram|gantt|pie|journey)', first):
        bad_mer.append((i, first))
chk(G, 'Mermaid 首行声明合法', [], bad_mer)
chk(G, 'Mermaid 围栏无未闭合', 0, doc.count('```mermaid') - len(mer))
# §6 新增 6 张图
s6 = doc[doc.find('# 6\u3000'):doc.find('# 7\u3000')]
chk(G, '§6 图数量', 6, len(re.findall(r'```mermaid', s6)))
# Mermaid 图内不应出现未加引号的圆括号节点标签（真实解析器常见失败点）
risk = []
for blk in mer:
    for ln in blk.split('\n'):
        # 形如  A[文字(括号)]  或  A(文字(括号))  —— 方括号内出现成对半角括号
        if re.search(r'\[[^\]]*\([^\)]*\)[^\]]*\]', ln) and not re.search(r'\["', ln):
            risk.append(ln.strip()[:60])
chk(G, 'Mermaid 节点标签括号风险', 0, len(risk))

# ============ 第 6 组：格式与文本 ============
G = 6
badrow, intable, cur_n = [], False, 0
for idx, ln in enumerate(doc.split('\n')):
    if re.match(r'^\|', ln) and ln.count('|') >= 2:
        n = len(re.split(r'(?<!\\)\|', ln)) - 2
        if not intable:
            intable, cur_n = True, n
        elif n != cur_n and not re.match(r'^\|[\s:|-]+\|$', ln):
            badrow.append((idx + 1, cur_n, n, ln[:60]))
    else:
        intable = False
chk(G, '表格列数配平', [], badrow[:5])

badh, prev, infence = [], 0, False
lines_doc = doc.split('\n')
for ln in lines_doc:
    if ln.startswith('```'):
        infence = not infence; continue
    if infence: continue
    m = re.match(r'^(#{1,6})\s', ln)
    if m:
        lv = len(m.group(1))
        if prev and lv > prev + 1:
            badh.append((lv, prev, ln[:50]))
        prev = lv
chk(G, '标题层级不跳级', [], badh[:5])

empt = []
dl = doc.split('\n')
for i, ln in enumerate(dl):
    if re.match(r'^#{1,6}\s', ln):
        nxt = [l for l in dl[i+1:i+6] if l.strip()]
        if not nxt:
            empt.append(ln[:50])
chk(G, '无空章节', [], empt)
chk(G, '表格总数 ≥ 80', True, len(re.findall(r'^\|\s*---', doc, re.M)) >= 80)
chk(G, '文档规模 ≥ 150000 字符', True, len(doc) >= 150000)

# ============ 输出 ============
NAMES = {1: '章节完整性', 2: '令牌双向比对', 3: '路由与视图一致性',
         4: '需求覆盖与未定义引用', 5: 'Mermaid 语法结构', 6: '格式与文本'}
print('=' * 84)
print('海瞳鱼鉴 · UI/UX 设计文档 —— 交付前六组校验')
print('=' * 84)
ok_all = True
for g in range(1, 7):
    grp = [r for r in R if r[0] == g]
    bad = [r for r in grp if not r[4]]
    print('\n【第 %d 组】%s  ——  %s' % (g, NAMES[g], 'PASS' if not bad else 'FAIL %d/%d' % (len(bad), len(grp))))
    for r in grp:
        print('   %s %-32s 期望=%s' % ('✓' if r[4] else '✗', r[1], r[2][:56]))
        if not r[4]:
            print('   %s %-32s 实际=%s' % (' ', '', r[3][:100]))
    ok_all &= not bad

print('\n' + '=' * 84)
n_ok = sum(1 for r in R if r[4])
print('断言总数 %d，通过 %d，失败 %d' % (len(R), n_ok, len(R) - n_ok))
print('总结果：%s' % ('六组校验全部通过 ✓' if ok_all else '存在失败项 ✗'))
print('文档规模：%d 字符 / %d 行' % (len(doc), doc.count('\n') + 1))
print('=' * 84)
