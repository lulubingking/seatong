# -*- coding: utf-8 -*-
"""数据集分辨率与格式体检

目的：确认"把图缩放到 224"是否会造成信息损失。
若大量图像原始尺寸远小于 224，则上采样无法增加信息，会压低精度上限，
需要在训练配置与文档风险项中如实登记。

抽样策略：每个类别最多抽 300 张（保证极小类全取），总计约 5,000 张，
用 PIL 只读文件头（不解码像素），速度快且内存安全。
"""

import io
import json
import os
import sys
from collections import Counter

from PIL import Image

_DATASET_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DATASET_DIR)
sys.path.insert(0, os.path.dirname(_DATASET_DIR))          # ml/
from species_meta import SPECIES  # noqa: E402
from config import DATA_ROOT, REPORTS_DIR  # noqa: E402  (可移植：由仓库位置推导)

OUT = os.path.join(REPORTS_DIR, 'dataset_health.json')
SAMPLE_PER_CLASS = 300


def main() -> int:
    print('=' * 76)
    print('数据集分辨率与格式体检（抽样，只读文件头）')
    print('=' * 76)
    print()

    all_w, all_h, all_mode, all_fmt = [], [], Counter(), Counter()
    small_than_224 = 0
    very_small = 0
    per_class = {}

    for sp in SPECIES:
        d = os.path.join(DATA_ROOT, sp.dir_name)
        files = sorted(os.listdir(d))
        step = max(1, len(files) // SAMPLE_PER_CLASS)
        sample = files[::step][:SAMPLE_PER_CLASS]

        ws, hs = [], []
        for fn in sample:
            try:
                with Image.open(os.path.join(d, fn)) as im:
                    w, h = im.size
                    all_mode[im.mode] += 1
                    all_fmt[im.format] += 1
            except Exception:
                continue
            ws.append(w); hs.append(h)
            all_w.append(w); all_h.append(h)
            short = min(w, h)
            if short < 224:
                small_than_224 += 1
            if short < 112:
                very_small += 1

        if ws:
            per_class[sp.dir_name] = {
                'sampled': len(ws),
                'w_min': min(ws), 'w_max': max(ws),
                'h_min': min(hs), 'h_max': max(hs),
                'short_min': min(min(ws[i], hs[i]) for i in range(len(ws))),
                'n_shorter_than_224': sum(1 for i in range(len(ws)) if min(ws[i], hs[i]) < 224),
            }
            print(f'  {sp.dir_name:8s} 抽 {len(ws):3d} 张 | 宽 {min(ws):4d}-{max(ws):4d} '
                  f'高 {min(hs):4d}-{max(hs):4d} | 短边<224 的 {per_class[sp.dir_name]["n_shorter_than_224"]:3d} 张')

    n = len(all_w)
    print()
    print(f'  抽样总数        : {n:,}')
    print(f'  尺寸范围        : 宽 {min(all_w)}-{max(all_w)} / 高 {min(all_h)}-{max(all_h)}')
    print(f'  短边中位数      : {sorted(min(all_w[i], all_h[i]) for i in range(n))[n // 2]}')
    print(f'  短边 < 224      : {small_than_224:,} = {small_than_224 / n * 100:.1f}%  （会被上采样）')
    print(f'  短边 < 112      : {very_small:,} = {very_small / n * 100:.1f}%  （信息严重不足）')
    print(f'  色彩模式        : {dict(all_mode)}')
    print(f'  文件格式        : {dict(all_fmt)}')
    print()

    ratio = small_than_224 / n
    if ratio > 0.5:
        verdict = '多数图像短边小于 224，缩放至上采样，精度上限受压'
    elif ratio > 0.2:
        verdict = '部分图像会被上采样，影响可控'
    else:
        verdict = '绝大多数图像尺寸充足，缩放不损失信息'
    print(f'  结论：{verdict}')
    print()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, 'w', encoding='utf-8') as f:
        json.dump({
            'sampled_total': n,
            'size_range': {'w': [min(all_w), max(all_w)], 'h': [min(all_h), max(all_h)]},
            'short_side_median': sorted(min(all_w[i], all_h[i]) for i in range(n))[n // 2],
            'n_short_lt_224': small_than_224,
            'pct_short_lt_224': round(ratio * 100, 2),
            'n_short_lt_112': very_small,
            'pct_short_lt_112': round(very_small / n * 100, 2),
            'modes': dict(all_mode),
            'formats': dict(all_fmt),
            'verdict': verdict,
            'per_class': per_class,
        }, f, ensure_ascii=False, indent=1)
    print(f'  报告已写入 {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
