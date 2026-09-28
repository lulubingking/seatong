# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · M3.5 剪枝实现正确性诊断与稀疏度-精度曲线

两个目的（缺一不可）：

A. **实现正确性验证**
   keep_map 取全集（稀疏度 0%）时，重建模型必须与基线**逐元素等价**。
   若此断言不通过，说明权重迁移存在 bug，则"剪枝后精度崩溃"的判断就不能成立，
   后续所有结论都会建立在错误前提上 —— 所以这一步必须先做，且必须先于结论。

B. **稀疏度-精度曲线（不微调的即时损失）**
   在 0% / 1% / 2% / 5% / 10% / 15% / 20% / 25% / 30% 上各测一次即时精度。
   用途：区分两种截然不同的结论 ——
     · 若小比例（1%~5%）也崩 → 说明方法/实现有问题，结论应指向修正方法；
     · 若只有高比例才崩 → 说明是"事后剪枝 + 高稀疏度"的固有性质，
       结论应指向"该手段在本模型上不适用于该稀疏度"。

方法学要点：评估集固定为 val 划分的前 N 张（预加载为张量，避免重复解码开销），
全部在 CPU 上执行以保证数值可比。

用法：
    python ml/optimize/diagnose_prune.py
    python ml/optimize/diagnose_prune.py --n-sub 600 --ratios 0,0.01,0.05,0.1,0.2,0.3
"""

import argparse
import os
import sys
import time

import numpy as np
import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from common import DEVICE_CPU, REPORTS_DIR, load_baseline, load_split, save_json  # noqa: E402
from fish_dataset import FishDataset  # noqa: E402
from preprocess import build_eval_transform  # noqa: E402
from prune_structured import STAGES, rebuild_with_channels, select_channels  # noqa: E402
from species_meta import NUM_CLASSES  # noqa: E402
from train import confusion_matrix, metrics_from_cm  # noqa: E402

DEFAULT_RATIOS = [0.0, 0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]


def load_subset(per_class: int) -> tuple[torch.Tensor, torch.Tensor]:
    """按类别**分层抽样**取评估子集（每类最多 per_class 张）。

    ⚠️ 踩坑记录：最初实现取的是 `split['val'][:N]`，结果这前 400 张**全部属于 class 0**
    —— 因为 split.json 的记录是按类别顺序排列的，而 fish_1 单独占全部样本的 44%。
    在单类子集上，acc 恒为 1.000（全预测同一类即全对），macro F1 也无意义，
    稀疏度曲线随之完全失真（30% 时 acc=0.000、25% 时 acc=1.000 都是假象，
    二者在真实分布下不可能同时成立）。
    本函数是修正版：必须分层，且要打印每类实际取样数以自证覆盖度。
    """
    split = load_split()
    by_cls: dict[int, list] = {}
    for r in split['val']:
        by_cls.setdefault(r['class_index'], []).append(r)

    recs, coverage = [], []
    for c in sorted(by_cls):
        take = by_cls[c][:per_class]
        recs.extend(take)
        coverage.append((c, len(take), len(by_cls[c])))

    ds = FishDataset(recs, build_eval_transform())
    xs, ys = [], []
    for i in range(len(ds)):
        t, y = ds[i]
        xs.append(t)
        ys.append(y)

    print(f'  分层抽样: {len(by_cls)} 类 / 共 {len(recs)} 张（每类上限 {per_class}）')
    short = [f'idx{c}:{t}/{a}' for c, t, a in coverage if t < per_class]
    if short:
        print(f'  样本不足 {per_class} 张的类别: {", ".join(short)}')
    return torch.stack(xs), torch.tensor(ys, dtype=torch.long)


def evaluate_tensor(model, x: torch.Tensor, y: torch.Tensor, bs: int = 32) -> dict:
    model.eval().to(DEVICE_CPU)
    preds = []
    with torch.inference_mode():
        for i in range(0, len(x), bs):
            preds.append(model(x[i:i + bs].to(DEVICE_CPU)).argmax(1).cpu())
    p = torch.cat(preds).numpy()
    cm = confusion_matrix(p, y.numpy(), NUM_CLASSES)
    return metrics_from_cm(cm)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-class', type=int, default=20,
                    help='每类取样上限（分层抽样；长尾小类不足则取全部）')
    ap.add_argument('--ratios', default=None, help='逗号分隔的剪枝比例列表')
    args = ap.parse_args()

    ratios = ([float(s) for s in args.ratios.split(',')] if args.ratios
              else DEFAULT_RATIOS)

    print('=' * 88)
    print(' 海瞳鱼鉴 · 剪枝实现正确性诊断 + 稀疏度-精度曲线')
    print('=' * 88)
    print(f'  评估子集: val 划分，按类别分层抽样（每类 ≤{args.per_class} 张）')
    print(f'  设备: CPU（数值可比）')
    print()

    x, y = load_subset(args.per_class)
    cnt = np.bincount(y.numpy(), minlength=NUM_CLASSES)
    print(f'  子集张量: {tuple(x.shape)} {x.dtype}')
    print(f'  类别覆盖: {int((cnt > 0).sum())}/{NUM_CLASSES} 类，'
          f'每类样本数 min={int(cnt[cnt > 0].min())} max={int(cnt.max())}')
    print()

    base, cfg, _ = load_baseline()
    base_m = evaluate_tensor(base, x, y)
    print(f'  基线即时精度: acc {base_m["accuracy"]:.6f}  macroF1 {base_m["macro_f1"]:.6f}')
    print()

    # ---- A. 实现正确性验证：0% 剪枝必须与基线逐元素等价 ----
    print('-' * 88)
    print(' A. 实现正确性验证（稀疏度 0% → 应与基线逐元素等价）')
    print('-' * 88)
    full_keep = {stage: list(range(planes)) for stage, _, planes in STAGES}
    m0 = rebuild_with_channels(base, full_keep)
    with torch.inference_mode():
        probe = x[:16]
        diff = (base(probe) - m0(probe)).abs()
    max_diff = float(diff.max())
    print(f'  16 张样本的最大逐元素绝对差: {max_diff:.3e}')
    verdict = 'PASS（实现正确）' if max_diff < 1e-4 else 'FAIL（权重迁移有 bug！）'
    print(f'  判定: {verdict}')
    m0_m = evaluate_tensor(m0, x, y)
    print(f'  0% 剪枝精度: acc {m0_m["accuracy"]:.6f}  macroF1 {m0_m["macro_f1"]:.6f}  '
          f'(Δacc {(m0_m["accuracy"]-base_m["accuracy"])*100:+.4f} pp / '
          f'ΔF1 {(m0_m["macro_f1"]-base_m["macro_f1"])*100:+.4f} pp)')
    if max_diff >= 1e-4:
        print('  ! 实现存在缺陷 —— 后续稀疏度曲线不可信，必须先修实现')
    print()

    # ---- B. 稀疏度-精度曲线 ----
    print('-' * 88)
    print(' B. 稀疏度-精度曲线（不微调的即时损失）')
    print('-' * 88)
    print(f'  {"目标稀疏度":>10s} {"实际稀疏度":>10s} {"参数减少":>9s} '
          f'{"acc":>10s} {"Δacc(pp)":>10s} {"macroF1":>10s} {"ΔF1(pp)":>10s}')
    print('  ' + '-' * 84)

    rows = []
    n_base = sum(p.numel() for p in base.parameters())
    t0 = time.time()
    for r in ratios:
        keep_map, sel = select_channels(base, r, verbose=False)
        m = rebuild_with_channels(base, keep_map)
        n_par = sum(p.numel() for p in m.parameters())
        met = evaluate_tensor(m, x, y)
        d_acc = (met['accuracy'] - base_m['accuracy']) * 100
        d_f1 = (met['macro_f1'] - base_m['macro_f1']) * 100
        rows.append({
            'requested_ratio': r,
            'actual_sparsity': sel['actual_sparsity'],
            'param_count': n_par,
            'param_reduction_pct': round((1 - n_par / n_base) * 100, 2),
            'accuracy': met['accuracy'],
            'macro_f1': met['macro_f1'],
            'delta_acc_pp': round(d_acc, 4),
            'delta_macro_f1_pp': round(d_f1, 4),
        })
        print(f'  {r:10.0%} {sel["actual_sparsity"]:10.2%} '
              f'{(1-n_par/n_base)*100:8.2f}% {met["accuracy"]:10.6f} {d_acc:+10.3f} '
              f'{met["macro_f1"]:10.6f} {d_f1:+10.3f}')

    print()
    print(f'  曲线耗时 {time.time()-t0:.1f}s')

    # ---- C. 崩溃点定位 ----
    print()
    print('-' * 88)
    print(' C. 崩溃点定位')
    print('-' * 88)
    thr = 1.0     # 控制线：1 个百分点
    safe = [r for r in rows if r['delta_macro_f1_pp'] >= -thr and r['requested_ratio'] > 0]
    if safe:
        best = max(safe, key=lambda r: r['requested_ratio'])
        print(f'  仍满足控制线（宏观 F1 回退 ≤{thr:.0f} pp）的最大稀疏度: '
              f'{best["requested_ratio"]:.0%}（ΔF1 {best["delta_macro_f1_pp"]:+.3f} pp）')
    else:
        print(f'  没有任何可控稀疏度能在不微调的情况下满足控制线')
        smallest = min([r for r in rows if r['requested_ratio'] > 0],
                       key=lambda r: r['requested_ratio'])
        print(f'  最小试验稀疏度 {smallest["requested_ratio"]:.0%} 的 ΔF1 已达 '
              f'{smallest["delta_macro_f1_pp"]:+.3f} pp')

    out = os.path.join(REPORTS_DIR, 'optimize_diagnose.json')
    save_json({
        'per_class': args.per_class,
        'subset_size': int(x.shape[0]),
        'device': DEVICE_CPU,
        'baseline': {'accuracy': base_m['accuracy'], 'macro_f1': base_m['macro_f1']},
        'equivalence_check': {'max_abs_diff': max_diff, 'passed': max_diff < 1e-4},
        'zero_prune': {'accuracy': m0_m['accuracy'], 'macro_f1': m0_m['macro_f1']},
        'curve': rows,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }, out)
    print()
    print(f'  结果: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
