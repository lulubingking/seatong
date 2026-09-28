# -*- coding: utf-8 -*-
"""微调网图池采集（并行版）—— 与 ood_web 基准集严格去重

基准纪律：ml/ood_web/（93 张）已冻结为 OOD 测试集，本脚本采集的图【不得】与之重叠，
去重键 = Commons 文件标题（manifest.json 里记录）。产出 ml/ood_web_tune/fish_{N}/。

与 collect_web_images.py 的差异：
  · ThreadPoolExecutor(8) 并行下载；搜索带 3 次重试；
  · 每类目标 40 张；仅作为微调数据，不做评估判据。
"""

import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(_ROOT, 'ml'))

from dataset.species_meta import SPECIES                 # noqa: E402

API = 'https://commons.wikimedia.org/w/api.php'
UA = {'User-Agent': 'SeaPupil-OOD-finetune/1.0 (local educational evaluation)'}
OUT = os.path.join(_ROOT, 'ml', 'ood_web_tune')
BENCH_MANIFEST = os.path.join(_ROOT, 'ml', 'ood_web', 'manifest.json')
PER_CLASS = 40
MIN_SIDE = 300
THUMB_W = 800
WORKERS = 8

SEARCH_OVERRIDE = {17: 'parrotfish'}


def api_search(term: str, limit: int = 50, retries: int = 3) -> list[dict]:
    qs = urllib.parse.urlencode({
        'action': 'query', 'format': 'json',
        'generator': 'search', 'gsrnamespace': '6',
        'gsrsearch': term, 'gsrlimit': str(limit),
        'prop': 'imageinfo', 'iiprop': 'url|size|mime',
        'iiurlwidth': str(THUMB_W),
    })
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(f'{API}?{qs}', headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode())
            pages = d.get('query', {}).get('pages', {})
            return sorted(pages.values(), key=lambda p: p.get('index', 999))
        except Exception as e:                      # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last                                        # type: ignore[misc]


def key_of_title(title: str) -> str:
    return os.path.splitext(title.replace('File:', ''))[0].lower()


def name_matches(tk: str, sp) -> bool:
    if sp.class_index == 17:
        return any(w in tk for w in ('scaridae', 'parrotfish', 'scarus', 'chlorurus',
                                     'hipposcarus', 'calotomus', 'sparisoma',
                                     'bolbometopon'))
    sci = sp.sci_name.lower()
    return sci in tk


def download_one(url: str, fp: str) -> bool:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        if len(raw) < 10_000:
            return False
        with open(fp, 'wb') as f:
            f.write(raw)
        return True
    except Exception:                                # noqa: BLE001
        return False


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    with open(BENCH_MANIFEST, encoding='utf-8') as f:
        bench = json.load(f)
    bench_titles = {t.lower() for v in bench.values() for t in v.get('titles', [])}

    manifest = {}
    total_saved = 0
    for sp in SPECIES:
        n = sp.class_index + 1
        cls_dir = os.path.join(OUT, f'fish_{n}')
        os.makedirs(cls_dir, exist_ok=True)

        terms = ([SEARCH_OVERRIDE[sp.class_index]] if sp.class_index in SEARCH_OVERRIDE
                 else [sp.sci_name])
        cands: list[dict] = []
        seen: set[str] = set()
        for term in terms:
            try:
                results = api_search(term)
            except Exception as e:                   # noqa: BLE001
                print(f'fish_{n} search FAIL after retries: {type(e).__name__}')
                continue
            for p in results:
                infos = (p.get('imageinfo') or [{}])[0]
                title = p.get('title', '')
                tk = key_of_title(title)
                if (tk in seen or tk in bench_titles or not title
                        or infos.get('mime') not in ('image/jpeg', 'image/png')
                        or min(infos.get('width', 0), infos.get('height', 0)) < MIN_SIDE
                        or not name_matches(tk, sp)):
                    continue
                url = infos.get('thumburl') or infos.get('url')
                if url:
                    seen.add(tk)
                    cands.append({'title': title, 'url': url})
        cands = cands[:PER_CLASS]

        jobs = []
        for i, c in enumerate(cands):
            ext = '.png' if c['url'].lower().endswith('.png') else '.jpg'
            fp = os.path.join(cls_dir, f'webt_{i:02d}{ext}')
            jobs.append((c, fp))
        saved = []
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(download_one, c['url'], fp): (c, fp) for c, fp in jobs}
            for fut in as_completed(futs):
                c, fp = futs[fut]
                if fut.result() or (os.path.exists(fp) and os.path.getsize(fp) > 10_000):
                    saved.append((c, fp))
        saved.sort(key=lambda x: x[1])
        manifest[f'fish_{n}'] = {
            'sci_name': sp.sci_name, 'cn_name': sp.cn_name,
            'saved': [os.path.basename(fp) for _c, fp in saved],
            'titles': [c['title'] for c, _fp in saved],
        }
        total_saved += len(saved)
        print(f'fish_{n:2d} {sp.sci_name:34s} cand={len(cands)} saved={len(saved)}',
              flush=True)

    with open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f'\n合计 {total_saved} 张 → {OUT}')


if __name__ == '__main__':
    main()
