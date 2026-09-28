# -*- coding: utf-8 -*-
"""预处理一致性单测 —— 证明训练/推理两条流水线产出逐元素相同的张量

PRD §10.4.2 要求【容差 0】。本测试用同一张源图，分别经由：
    A. 训练侧的验证分支（build_eval_transform）
    B. 推理侧入口（preprocess_for_inference）
断言两点：
    1. 两条路径输出的张量 torch.equal() 为 True（严格逐元素相等，不是 allclose）
    2. 同一输入重复调用结果完全一致（确定性）
若任一失败，说明预处理出现了分裂，必须立即修 —— 这是最容易在后期酿成
"训练指标很好、上线效果崩坏" 的隐蔽缺陷。

用法：python test_preprocess_parity.py
"""

import os
import sys

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))                 # ml/
from preprocess import (  # noqa: E402
    build_eval_transform,
    load_image_rgb,
    preprocess_for_inference,
)
from species_meta import SPECIES  # noqa: E402
from config import DATA_ROOT  # noqa: E402  (可移植：由仓库位置推导)

R = []


def chk(name: str, ok: bool, detail: str = ''):
    R.append((name, bool(ok), detail))


def main() -> int:
    print('=' * 76)
    print('预处理一致性校验 · PRD §10.4.2（容差 0）')
    print('=' * 76)
    print()

    # 抽样：覆盖头部大类、中部类、极小类，以及不同图像模式
    probe_dirs = ['fish_1', 'fish_4', 'fish_21', 'fish_18', 'fish_23', 'fish_20']
    transform = build_eval_transform()

    for dir_name in probe_dirs:
        d = os.path.join(DATA_ROOT, dir_name)
        if not os.path.isdir(d):
            chk(f'{dir_name} 目录存在', False, d)
            continue

        sp = next(s for s in SPECIES if s.dir_name == dir_name)
        files = sorted(os.listdir(d))[:3]   # 每类取前 3 张

        for fname in files:
            fp = os.path.join(d, fname)
            tag = f'{dir_name}/{fname}'

            try:
                # ---- 路径 A：训练侧的验证分支 ----
                img_a = load_image_rgb(fp)
                t_a = transform(img_a).unsqueeze(0).contiguous()

                # ---- 路径 B：推理侧入口 ----
                t_b = preprocess_for_inference(fp)

                # 形状与 dtype
                chk(f'[{tag}] 形状一致', t_a.shape == t_b.shape == (1, 3, 224, 224),
                    f'A={tuple(t_a.shape)} B={tuple(t_b.shape)}')
                chk(f'[{tag}] dtype 一致', t_a.dtype == t_b.dtype == torch.float32,
                    f'A={t_a.dtype} B={t_b.dtype}')

                # 核心断言：严格逐元素相等（非 allclose）
                eq = torch.equal(t_a, t_b)
                maxdiff = (t_a - t_b).abs().max().item()
                chk(f'[{tag}] 逐元素相等(容差 0)', eq, f'max|Δ|={maxdiff}')

                # 确定性：重复调用结果一致
                t_b2 = preprocess_for_inference(fp)
                chk(f'[{tag}] 推理路径确定性', torch.equal(t_b, t_b2),
                    '重复调用结果不同')

                # 值域合理性（归一化后应在约 [-2.2, 2.7]）
                ok_range = -3.0 <= t_b.min().item() and t_b.max().item() <= 3.0
                chk(f'[{tag}] 值域合理', ok_range,
                    f'min={t_b.min():.4f} max={t_b.max():.4f}')

            except Exception as e:
                chk(f'[{tag}] 无异常', False, f'{type(e).__name__}: {e}')

    # 跨来源一致性：路径 vs bytes（后端上传是 bytes，训练是路径）
    print()
    print('  -- 跨来源一致性（bytes 上传 vs 路径读取）--')
    for dir_name in ['fish_1', 'fish_11']:
        d = os.path.join(DATA_ROOT, dir_name)
        fname = sorted(os.listdir(d))[0]
        fp = os.path.join(d, fname)
        with open(fp, 'rb') as f:
            raw = f.read()
        t_path = preprocess_for_inference(fp)
        t_bytes = preprocess_for_inference(raw)
        chk(f'[{dir_name}] 路径 vs bytes 逐元素相等', torch.equal(t_path, t_bytes),
            f'max|Δ|={(t_path - t_bytes).abs().max().item()}')

    # ---------------- 汇总 ----------------
    print()
    print('=' * 76)
    passed = sum(1 for _, ok, _ in R if ok)
    failed = [r for r in R if not r[1]]
    for name, ok, detail in R:
        mark = '✓' if ok else '✗'
        line = f'  {mark} {name}'
        if not ok and detail:
            line += f'\n      实际: {detail}'
        if not ok:
            print(line)
    print()
    print(f'断言总数 {len(R)}，通过 {passed}，失败 {len(failed)}')
    if failed:
        print('结果：存在失败项 ✗')
        return 1
    print('结果：预处理一致性校验全部通过 ✓ —— 训练/推理张量逐元素相同，容差 0')
    return 0


if __name__ == '__main__':
    sys.exit(main())
