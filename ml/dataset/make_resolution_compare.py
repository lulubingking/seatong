# -*- coding: utf-8 -*-
"""生成分辨率对照图 —— 直观呈现"上采样损失"

对每个抽样类别取一张图，并排展示：
  ① 原始尺寸（按真实像素 1:1 缩放显示在固定画框中）
  ② 经 Resize(256)+CenterCrop(224) 后回读的等效视觉
若 ② 相对 ① 明显更"糊"或主体被裁掉，即证明该流水线有损。

输出：ml/reports/resolution_compare.png
"""

import os
import sys

from PIL import Image, ImageDraw

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))                 # ml/

from preprocess import build_eval_transform, load_image_rgb, denormalize  # noqa: E402
from species_meta import SPECIES  # noqa: E402
from config import DATA_ROOT, REPORTS_DIR  # noqa: E402  (可移植：由仓库位置推导)

OUT = os.path.join(REPORTS_DIR, 'resolution_compare.png')

# 选取有代表性的类别：头部大类 / 中部 / 极小类 / 单色背景类
PICK = ['fish_1', 'fish_4', 'fish_7', 'fish_14', 'fish_18', 'fish_21']
BOX = 224          # 每格画框边长
PAD = 10
LABEL_H = 40


def fit_to_box(im: Image.Image, box: int, upscale: bool) -> Image.Image:
    """把图放入 box×box 画框：upscale=False 时按原始像素不放大（仅缩小），
    upscale=True 时拉满画框（模拟训练时的上采样行为）。"""
    w, h = im.size
    if not upscale:
        s = min(box / w, box / h, 1.0)      # 只允许缩小
    else:
        s = box / max(w, h)
    nw, nh = max(1, int(w * s)), max(1, int(h * s))
    return im.resize((nw, nh), Image.LANCZOS)


def main() -> int:
    tf = build_eval_transform()

    cols = len(PICK)
    W = PAD + cols * (BOX + PAD)
    H = LABEL_H + BOX * 2 + PAD * 3 + LABEL_H * 2

    canvas = Image.new('RGB', (W, H), (247, 249, 252))
    dr = ImageDraw.Draw(canvas)

    dr.text((PAD, 8), '上排：原始尺寸（1:1，不放大，仅缩小以适应画框）', fill=(27, 36, 48))
    dr.text((PAD, LABEL_H + BOX + PAD * 2 + 6),
            '下排：经 Resize(256) → CenterCrop(224) 后的实际训练输入', fill=(180, 35, 24))

    for i, dir_name in enumerate(PICK):
        sp = next(s for s in SPECIES if s.dir_name == dir_name)
        d = os.path.join(DATA_ROOT, dir_name)
        fname = sorted(os.listdir(d))[0]
        raw = Image.open(os.path.join(d, fname))
        raw.load()
        img = load_image_rgb(raw)

        x = PAD + i * (BOX + PAD)

        # 上排：原始（不放大）
        top = fit_to_box(img, BOX, upscale=False)
        c1 = Image.new('RGB', (BOX, BOX), (255, 255, 255))
        c1.paste(top, ((BOX - top.width) // 2, (BOX - top.height) // 2))
        canvas.paste(c1, (x, LABEL_H))
        dr.rectangle([x, LABEL_H, x + BOX - 1, LABEL_H + BOX - 1], outline=(226, 232, 240))
        dr.text((x + 2, LABEL_H - 13), f'{sp.dir_name} {img.size[0]}x{img.size[1]}', fill=(90, 100, 114))

        # 下排：训练实际输入（反归一化回看）
        t = tf(img).unsqueeze(0)
        back = denormalize(t)[0].permute(1, 2, 0).numpy()
        import numpy as np
        arr = (back * 255).astype('uint8')
        bottom = Image.fromarray(arr).resize(fit_to_box(img, BOX, True).size, Image.LANCZOS)
        c2 = Image.new('RGB', (BOX, BOX), (255, 255, 255))
        c2.paste(bottom, ((BOX - bottom.width) // 2, (BOX - bottom.height) // 2))
        canvas.paste(c2, (x, LABEL_H + BOX + PAD))
        dr.rectangle([x, LABEL_H + BOX + PAD, x + BOX - 1, LABEL_H + BOX + PAD + BOX - 1],
                     outline=(180, 35, 24))
        dr.text((x + 2, LABEL_H + BOX * 2 + PAD * 2 + 6), f'{sp.cn_name}', fill=(90, 100, 114))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    canvas.save(OUT)
    print(f'对照图已生成: {OUT}')
    print(f'尺寸: {canvas.size[0]}×{canvas.size[1]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
