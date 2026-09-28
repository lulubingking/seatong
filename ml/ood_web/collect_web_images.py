# -*- coding: utf-8 -*-
"""分布外（OOD）网图测试集采集 —— Wikimedia Commons

目的：验证「训练集同源图片准、网图不准」的分布外泛化假设，
为 docs/海瞳鱼鉴-分布外网图评估报告.md 提供实测数据。

方法：
  · 逐类按拉丁学名检索 Commons File 命名空间（generator=search, gsrnamespace=6）；
  · 过滤：mime ∈ {jpeg,png}、短边 ≥ 300px、文件名含学名（降低地图/示意图误入）；
  · 每类最多 5 张，下载 800px 缩略图（足够 224 推理，节省带宽）；
  · fish_18（Scaridae，科级未定种）改用 'parrotfish' 检索。

许可说明：Commons 图片均为自由许可（CC/PD），仅用于本地教学评估，不随产品分发。
"""

import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))          # 项目根
sys.path.insert(0, os.path.join(_ROOT, 'ml'))

from dataset.species_meta import SPECIES                 # noqa: E402

API = 'https://commons.wikimedia.org/w/api.php'
UA = {'User-Agent': 'SeaPupil-OOD-eval/1.0 (local educational evaluation)'}
OUT = os.path.join(_HERE)
PER_CLASS = 5
MIN_SIDE = 300
THUMB_W = 800

# 科级 / 学名检索易空时的兜底词（按 class_index）
SEARCH_OVERRIDE = {
    17: 'parrotfish',            # Scaridae 科级
    6: 'Myripristis kuntee OR Myripristis berndti',   # kuntee 常与近缘种混拍，仍以文件名过滤
}


def api_search(term: str, limit: int = 30) -> list[dict]:
    qs = urllib.parse.urlencode({
        'action': 'query', 'format': 'json',
        'generator': 'search', 'gsrnamespace': '6',
        'gsrsearch': term, 'gsrlimit': str(limit),
        'prop': 'imageinfo', 'iiprop': 'url|size|mime',
        'iiurlwidth': str(THUMB_W),
    })
    req = urllib.request.Request(f'{API}?{qs}', headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode())
    pages = d.get('query', {}).get('pages', {})
    return sorted(pages.values(), key=lambda p: p.get('index', 999))


def name_variants(sp) -> list[str]:
    """学名检索词序列：精确学名 → 兜底词 → 去命名人的属名。"""
    out = [sp.sci_name]
    if sp.class_index in SEARCH_OVERRIDE:
        out.insert(0, SEARCH_OVERRIDE[sp.class_index])
    genus = sp.sci_name.split()[0] if ' ' in sp.sci_name else sp.sci_name
    out.append(genus)
    return out


def key_of_title(title: str) -> str:
    return os.path.splitext(title.replace('File:', ''))[0].lower()


def name_matches(title_key: str, sp) -> bool:
    """文件名须出现学名（或科名/属名兜底），过滤地图与无关文档。"""
    tk = title_key
    if sp.class_index == 17:
        return any(w in tk for w in ('scaridae', 'parrotfish', 'scarus', 'chlorurus',
                                     'hipposcarus', 'calotomus', 'sparisoma', 'bolbometopon'))
    sci = sp.sci_name.lower()
    return sci in tk or sci.replace(' ', '_') in tk


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    manifest = {}
    for sp in SPECIES:
        n = sp.class_index + 1
        cls_dir = os.path.join(OUT, f'fish_{n}')
        os.makedirs(cls_dir, exist_ok=True)
        got: list[dict] = []
        seen_titles: set[str] = set()
        for term in name_variants(sp):
            try:
                results = api_search(term)
            except Exception as e:
                print(f'fish_{n} search[{term}] FAIL {type(e).__name__}: {e}')
                time.sleep(1.0)
                continue
            for p in results:
                if len(got) >= PER_CLASS:
                    break
                infos = (p.get('imageinfo') or [{}])[0]
                mime = infos.get('mime', '')
                w, h = infos.get('width', 0), infos.get('height', 0)
                title = p.get('title', '')
                tk = key_of_title(title)
                if tk in seen_titles:
                    continue
                if mime not in ('image/jpeg', 'image/png'):
                    continue
                if min(w, h) < MIN_SIDE:
                    continue
                if not name_matches(tk, sp):
                    continue
                url = infos.get('thumburl') or infos.get('url')
                if not url:
                    continue
                seen_titles.add(tk)
                got.append({'title': title, 'url': url, 'w': w, 'h': h})
            if len(got) >= PER_CLASS:
                break
        # 下载
        saved = []
        for i, g in enumerate(got):
            ext = '.png' if g['url'].lower().endswith('.png') else '.jpg'
            fp = os.path.join(cls_dir, f'web_{i:02d}{ext}')
            if os.path.exists(fp) and os.path.getsize(fp) > 10_000:
                saved.append(fp)
                continue
            try:
                req = urllib.request.Request(g['url'], headers=UA)
                with urllib.request.urlopen(req, timeout=25) as r:
                    raw = r.read()
                if len(raw) < 10_000:
                    continue
                with open(fp, 'wb') as f:
                    f.write(raw)
                saved.append(fp)
                time.sleep(0.3)
            except Exception as e:
                print(f'fish_{n} download FAIL {g["title"]}: {type(e).__name__}')
        manifest[f'fish_{n}'] = {
            'sci_name': sp.sci_name, 'cn_name': sp.cn_name,
            'found': len(got), 'saved': [os.path.basename(s) for s in saved],
            'titles': [g['title'] for g in got[:len(saved)]],
        }
        print(f'fish_{n:2d} {sp.sci_name:32s} found={len(got)} saved={len(saved)}')
        time.sleep(0.4)
    with open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    total = sum(len(v['saved']) for v in manifest.values())
    classes = sum(1 for v in manifest.values() if v['saved'])
    print(f'\n合计：{total} 张，覆盖 {classes}/23 类 → {OUT}')


if __name__ == '__main__':
    main()
