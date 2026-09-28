# -*- coding: utf-8 -*-
"""网图（分布外）评估 —— 用交付模型实测非同源图片的表现

对照两种预处理：
  · prod    ：线上同款 preprocess_for_inference（短边256 → 中心裁剪224）
  · resize  ：整图直接缩放 224×224（诊断「中心裁剪裁掉网图鱼体」的假设）

判定：预期标签 = 采集目录 fish_{N}（class_index = N-1）。
输出 ml/reports/ood_web_eval.json，供分布外评估报告引用。
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for p in (_ROOT, os.path.join(_ROOT, 'ml')):
    if p not in sys.path:
        sys.path.insert(0, p)

import torch                                                    # noqa: E402
from PIL import Image                                           # noqa: E402
from torchvision import transforms                              # noqa: E402
from torchvision.transforms import InterpolationMode            # noqa: E402

from dataset.preprocess import (                                # noqa: E402
    IMAGENET_MEAN, IMAGENET_STD, preprocess_for_inference)
from dataset.species_meta import SPECIES                        # noqa: E402
from optimize.common import load_baseline                       # noqa: E402

OUT_JSON = os.path.join(_ROOT, 'ml', 'reports', 'ood_web_eval.json')
RESIZE_TF = transforms.Compose([
    transforms.Resize((224, 224), interpolation=InterpolationMode.BILINEAR),
    transforms.ToTensor(),
    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
])


@torch.inference_mode()
def predict(model, img: Image.Image, mode: str) -> tuple[int, float, list[int]]:
    if mode == 'prod':
        tensor = preprocess_for_inference(img)
    else:
        tensor = RESIZE_TF(img.convert('RGB')).unsqueeze(0)
    logits = model(tensor)
    probs = torch.softmax(logits.float(), dim=1)[0]
    vals, idxs = torch.topk(probs, 5)
    return int(idxs[0]), float(vals[0]), [int(i) for i in idxs]


def main() -> None:
    model, _cfg, _ckpt = load_baseline()
    rows = []
    agg = {m: {'n': 0, 'top1': 0, 'top5': 0, 'conf': 0.0}
           for m in ('prod', 'resize')}
    for sp in SPECIES:
        n = sp.class_index + 1
        d = os.path.join(_HERE, f'fish_{n}')
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            fp = os.path.join(d, fn)
            try:
                img = Image.open(fp)
                img.load()
            except Exception as e:
                rows.append({'image': f'fish_{n}/{fn}', 'error': str(e)[:120]})
                continue
            rec = {'image': f'fish_{n}/{fn}', 'true': sp.class_index}
            for mode in ('prod', 'resize'):
                top1, conf, top5 = predict(model, img, mode)
                rec[mode] = {'top1': top1, 'conf': round(conf, 4),
                             'top5': top5, 'hit1': top1 == sp.class_index,
                             'hit5': sp.class_index in top5}
                a = agg[mode]
                a['n'] += 1
                a['top1'] += rec[mode]['hit1']
                a['top5'] += rec[mode]['hit5']
                a['conf'] += conf
            rows.append(rec)
            print(f'{rec["image"]:22s} prod: {rec["prod"]["top1"]:2d} '
                  f'({rec["prod"]["conf"]:.2f})  resize: {rec["resize"]["top1"]:2d} '
                  f'({rec["resize"]["conf"]:.2f})')

    summary = {}
    for m, a in agg.items():
        summary[m] = {
            'n': a['n'],
            'top1_acc': round(a['top1'] / a['n'], 4) if a['n'] else None,
            'top5_acc': round(a['top5'] / a['n'], 4) if a['n'] else None,
            'mean_conf': round(a['conf'] / a['n'], 4) if a['n'] else None,
        }
    # 同分布对照（M1 ep11 验证集冻结值，来自 checkpoint metrics）
    summary['indoor_reference'] = {
        'source': 'M1_main_224 ep11 验证集（同分布）',
        'acc': 0.997074, 'macro_f1': 0.975185,
    }
    out = {'summary': summary, 'rows': rows}
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('\n==== 汇总 ====')
    for m in ('prod', 'resize'):
        s = summary[m]
        print(f'{m:7s} n={s["n"]}  top1={s["top1_acc"]}  top5={s["top5_acc"]}  '
              f'mean_conf={s["mean_conf"]}')
    print(f'saved -> {OUT_JSON}')


if __name__ == '__main__':
    main()
