# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · M3.5 一键编排

按依赖顺序执行完整流程：

  1. quantize.py            量化（动态 int8 / FX 静态 int8）
  2. prune_structured.py    结构化剪枝 + 微调
  3. compare.py             同一测试集对照复测与达标判定

之所以把三步分开而不是一个脚本跑到底：
  · 剪枝微调耗 GPU 时间（约 10 分钟），失败时不应连带重跑量化；
  · 每一阶段都独立产出可复现的模型与 meta.json，便于单独复核；
  · 若中途判定「该手段不适用」，可直接终止，不必跑完整个流水线。

用法：
    python ml/optimize/run_all.py                    # 全流程
    python ml/optimize/run_all.py --ratio 0.15       # 换剪枝比例
    python ml/optimize/run_all.py --skip-prune       # 只做量化与复测
"""

import argparse
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(title: str, args: list[str]) -> int:
    print()
    print('#' * 96)
    print(f'# {title}')
    print('#' * 96)
    t0 = time.time()
    rc = subprocess.call([PY, '-u'] + args)
    print(f'  → 返回码 {rc}，耗时 {time.time() - t0:.1f}s')
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ratio', type=float, default=0.30)
    ap.add_argument('--ft-epochs', type=int, default=8)
    ap.add_argument('--skip-quantize', action='store_true')
    ap.add_argument('--skip-prune', action='store_true')
    ap.add_argument('--skip-compare', action='store_true')
    ap.add_argument('--protect-first-layer', action='store_true')
    args = ap.parse_args()

    t_all = time.time()
    codes = {}

    if not args.skip_quantize:
        codes['quantize'] = run('1/3 量化（动态 int8 + FX 静态 int8）',
                                [os.path.join(_HERE, 'quantize.py'), '--mode', 'both'])
        if codes['quantize'] != 0:
            print('  ! 量化阶段失败，终止')
            return codes['quantize']

    if not args.skip_prune:
        cmd = [os.path.join(_HERE, 'prune_structured.py'),
               '--ratio', str(args.ratio), '--ft-epochs', str(args.ft_epochs), '--cpu-eval']
        if args.protect_first_layer:
            cmd.append('--protect-first-layer')
        codes['prune'] = run(f'2/3 结构化剪枝 ratio={args.ratio}', cmd)
        if codes['prune'] != 0:
            print('  ! 剪枝阶段失败，继续做复测（已有产物）')

    if not args.skip_compare:
        codes['compare'] = run('3/3 同一测试集对照复测与判定',
                               [os.path.join(_HERE, 'compare.py')])

    print()
    print('=' * 96)
    print(f' 全流程结束，总耗时 {(time.time() - t_all)/60:.1f} 分钟')
    for k, v in codes.items():
        print(f'   {k:10s} 返回码 {v}')
    print('=' * 96)
    return 0 if all(v == 0 for v in codes.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
