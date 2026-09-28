# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · M3.5 对照复测与达标判定

PRD §7.5 复测要求：「优化后必须在**同一测试集**上完整复测，
复测结果并入评估报告，形成『优化前 / 优化后』对照」；
控制线：「总体准确率回退 ≤1 个百分点、宏观 F1 回退 ≤1 个百分点，
超标即放弃该优化手段，保留未优化的基线模型」。

本脚本把量化与剪枝的产物拉到同一把尺子上：

  评估口径统一（重要）
    · 数据：split.json 的 test 划分，2734 张，一次冻结、四模型共用；
    · 预处理：preprocess.build_eval_transform()，确定性、无随机性；
    · 指标：train.metrics_from_cm()，与训练期同源；
    · **精度评估一律在 CPU 上执行** —— 因为 int8 量化模型只能跑 CPU，
      若基线用 GPU、量化用 CPU，浮点累加顺序不同会引入不可比的微小偏差。

  耗时口径
    · CPU 前向 p50 对所有模型测量（可比）；
    · GPU 前向 p50 仅对能在 CUDA 上运行的模型测量（量化模型跳过）；
    · 另测「冷加载耗时」，用于判定"模型体积或加载时间是否成为瓶颈"。

用法：
    python ml/optimize/compare.py
    python ml/optimize/compare.py --skip-gpu
"""

import argparse
import os
import sys
import time

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from common import (  # noqa: E402
    BASELINE_CKPT, DEVICE_CPU, DEVICE_GPU, MODELS_DIR, REPORTS_DIR,
    bench_forward, ensure_dirs, evaluate, is_quantized, load_baseline,
    param_count, rebuild_static_int8_fx, save_json, serialized_bytes, test_set_size,
)
from prune_structured import rebuild_with_channels  # noqa: E402

HARD_ACC = 0.85
HARD_F1 = 0.82
CONTROL_PP = 1.0        # 精度回退控制线（百分点）

ARTIFACTS = [
    {
        'key': 'baseline', 'kind': 'baseline',
        'label': '基线 M1（float32）',
        'path': BASELINE_CKPT,
        'method': '无优化',
    },
    {
        'key': 'dynamic_int8', 'kind': 'module',
        'label': '动态量化 int8（仅全连接层）',
        'path': os.path.join(MODELS_DIR, 'M1_main_224_dynamic_int8', 'model.pt'),
        'method': 'dynamic_int8_linear',
    },
    {
        'key': 'static_int8', 'kind': 'fx_static',
        'label': '静态量化 int8（Conv+Linear）',
        'path': os.path.join(MODELS_DIR, 'M1_main_224_static_int8', 'state_dict.pt'),
        'method': 'static_int8_fx_x86',
    },
    {
        'key': 'pruned30', 'kind': 'pruned',
        'label': '结构化剪枝 30% + 微调',
        'path': os.path.join(MODELS_DIR, 'M1_main_224_pruned30_ft', 'best.pt'),
        'method': 'structured_channel_pruning+ft',
    },
    {
        'key': 'pruned30_protectstem', 'kind': 'pruned',
        'label': '结构化剪枝 30%（保护首层）+ 微调',
        'path': os.path.join(MODELS_DIR, 'M1_main_224_pruned30_protectstem_ft', 'best.pt'),
        'method': 'structured_channel_pruning(protect_stem)+ft',
    },
]


def load_artifact(a: dict):
    """返回 (model, cfg, exists)。剪枝模型需按 keep_map 重建空壳再灌权重。"""
    p = a['path']
    if not os.path.exists(p):
        return None, None, False

    if a['kind'] == 'baseline':
        m, cfg, _ = load_baseline(p)
        return m, cfg, True

    if a['kind'] == 'module':
        obj = torch.load(p, map_location='cpu', weights_only=False)
        return obj.eval(), None, True

    if a['kind'] == 'fx_static':
        # FX 量化模型不能整模块 pickle 往返，必须按配方重建后灌 state_dict
        base, cfg, _ = load_baseline()
        m = rebuild_static_int8_fx(base, state_path=p)
        return m.eval(), cfg, True

    if a['kind'] == 'pruned':
        ck = torch.load(p, map_location='cpu', weights_only=False)
        base, cfg, _ = load_baseline()
        m = rebuild_with_channels(base, ck['keep_map'])
        m.load_state_dict(ck['state_dict'], strict=True)
        return m.eval(), cfg, True

    raise ValueError(f'未知产物类型: {a["kind"]}')


def measure_load_seconds(a: dict) -> float:
    t0 = time.perf_counter()
    load_artifact(a)
    return round(time.perf_counter() - t0, 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-gpu', action='store_true')
    ap.add_argument('--skip-missing', action='store_true', default=True)
    args = ap.parse_args()

    ensure_dirs()
    print('=' * 96)
    print(' 海瞳鱼鉴 · M3.5 对照复测（同一测试集）')
    print('=' * 96)
    print(f'  测试集: split.json → test，{test_set_size():,} 张（冻结，四模型共用）')
    print(f'  精度评估设备: CPU（统一口径，因 int8 模型只能跑 CPU）')
    print(f'  控制线: 准确率与宏观 F1 回退均 ≤ {CONTROL_PP:.1f} 个百分点')
    print(f'  硬指标: 准确率 ≥ {HARD_ACC} / 宏观 F1 ≥ {HARD_F1}')
    print()

    records = []
    for a in ARTIFACTS:
        model, cfg, exists = load_artifact(a)
        if not exists:
            print(f'  - 跳过 {a["label"]}（产物不存在: {a["path"]}）')
            continue

        quant = is_quantized(model)
        print(f'  评估 {a["label"]} ...')
        t_metrics, _, sec = evaluate(model, DEVICE_CPU)
        cpu_bench = bench_forward(model, DEVICE_CPU)

        gpu_bench = None
        if not quant and not args.skip_gpu and torch.cuda.is_available():
            gpu_bench = bench_forward(model, DEVICE_GPU)

        rec = {
            'key': a['key'],
            'label': a['label'],
            'method': a['method'],
            'path': a['path'],
            'exists': True,
            'is_quantized': quant,
            'param_count': param_count(model),
            'serialized_mb': round(
                (os.path.getsize(a['path']) / 1024 ** 2) if a['kind'] == 'fx_static'
                else (serialized_bytes(model) / 1024 ** 2), 3),
            'file_mb': round(os.path.getsize(a['path']) / 1024 ** 2, 3),
            'load_seconds': measure_load_seconds(a),
            'bench_cpu_ms': cpu_bench,
            'bench_gpu_ms': gpu_bench,
            'accuracy': t_metrics['accuracy'],
            'macro_f1': t_metrics['macro_f1'],
            'weighted_f1': t_metrics['weighted_f1'],
            'per_class_f1': t_metrics['per_class_f1'],
            'per_class_support': t_metrics['per_class_support'],
            'eval_seconds_cpu': round(sec, 1),
        }
        records.append(rec)
        print(f'      acc {rec["accuracy"]:.6f}  macroF1 {rec["macro_f1"]:.6f}  '
              f'体积 {rec["serialized_mb"]:.3f} MB  CPU {cpu_bench["p50_ms"]:.3f} ms'
              f'{"  GPU " + format(gpu_bench["p50_ms"], ".3f") + " ms" if gpu_bench else ""}')

    # ---- 判定 ----
    base = next((r for r in records if r['key'] == 'baseline'), None)
    if base is None:
        print('  ! 未找到基线记录，无法判定')
        return 1

    for r in records:
        d_acc = (r['accuracy'] - base['accuracy']) * 100
        d_f1 = (r['macro_f1'] - base['macro_f1']) * 100
        r['delta_acc_pp'] = round(d_acc, 3)
        r['delta_macro_f1_pp'] = round(d_f1, 3)
        r['size_change_pct'] = round((r['serialized_mb'] / base['serialized_mb'] - 1) * 100, 2)
        r['cpu_ms_change_pct'] = round(
            (r['bench_cpu_ms']['p50_ms'] / base['bench_cpu_ms']['p50_ms'] - 1) * 100, 2)
        r['within_control_line'] = (d_acc >= -CONTROL_PP) and (d_f1 >= -CONTROL_PP)
        r['hard_targets_met'] = (r['accuracy'] >= HARD_ACC) and (r['macro_f1'] >= HARD_F1)
        # 注意命名：这里只判定「精度维度」是否可采纳。
        # PRD §7.5 还有第二道门 —— 优化手段仅在推理耗时或模型体积未达目标时才启用
        # （"不得为优化而优化"）。两道门都过才叫"启用"。本字段不含第二道门的判定，
        # 以免出现"脚本说可采纳、报告说不启用"的表面对立。
        r['precision_adoptable'] = bool(r['within_control_line'] and r['hard_targets_met'])

    print()
    print('=' * 96)
    print(' 对照表（同一测试集，CPU 评估口径）')
    print('=' * 96)
    hdr = (f'  {"模型":32s} {"体积MB":>8s} {"Δ体积":>8s} {"CPU p50":>9s} {"ΔCPU":>8s} '
           f'{"acc":>9s} {"Δacc(pp)":>11s} {"macroF1":>9s} {"ΔF1(pp)":>10s} {"控制线":>7s} '
           f'{"精度可采纳":>10s}')
    print(hdr)
    print('  ' + '-' * 94)
    for r in records:
        print(f'  {r["label"]:32s} {r["serialized_mb"]:8.3f} {r["size_change_pct"]:+7.2f}% '
              f'{r["bench_cpu_ms"]["p50_ms"]:9.3f} {r["cpu_ms_change_pct"]:+7.2f}% '
              f'{r["accuracy"]:9.6f} {r["delta_acc_pp"]:+11.3f} '
              f'{r["macro_f1"]:9.6f} {r["delta_macro_f1_pp"]:+10.3f} '
              f'{"通过" if r["within_control_line"] else "超标":>7s} '
              f'{"是" if r["precision_adoptable"] else "否":>10s}')
    print()
    print('  "精度可采纳"仅表示通过 PRD §7.5 的精度控制线与硬指标。')
    print('  PRD §7.5 另有一道门：优化手段仅在推理耗时或模型体积**未达目标时**才启用')
    print('  （原文"不得为优化而优化"）。本项目 GPU 纯前向 2.28 ms、端到端 44–55 ms')
    print('  （预算 3000 ms），体积 42.77 MB、冷加载 0.115 s —— 均不构成瓶颈，')
    print('  故最终结论为「维持基线、不启用优化」。详见')
    print('  docs/海瞳鱼鉴-模型优化与复测报告.md 第一节与第七节。')

    if base.get('bench_gpu_ms'):
        print()
        print('  GPU 前向 p50（仅非量化模型）:')
        for r in records:
            if r['bench_gpu_ms']:
                print(f'    {r["label"]:32s} {r["bench_gpu_ms"]["p50_ms"]:7.3f} ms')

    print()
    print('  冷加载耗时（含 torch.load + 建模 + 灌权重）:')
    for r in records:
        print(f'    {r["label"]:32s} {r["load_seconds"]:7.3f} s')

    out = {
        'baseline_ckpt': BASELINE_CKPT,
        'test_set_size': test_set_size(),
        'eval_device': DEVICE_CPU,
        'control_line_pp': CONTROL_PP,
        'hard_targets': {'accuracy': HARD_ACC, 'macro_f1': HARD_F1},
        'judgement_scope': {
            'precision_adoptable': '仅按 PRD §7.5 精度控制线（回退 ≤1 pp）与硬指标判定',
            'enable_condition': (
                'PRD §7.5 另有一道门：优化手段仅在推理耗时或模型体积未达目标时启用'
                '（原文「不得为优化而优化」）。本项目实测 GPU 纯前向约 2.28 ms、'
                '端到端 44–55 ms（预算 3000 ms）、体积 42.77 MB、冷加载 0.115 s，'
                '均不构成瓶颈 —— 该道门不成立。'),
            'final_decision': '维持基线 M1（float32），不启用任何优化手段；'
                              '详见 docs/海瞳鱼鉴-模型优化与复测报告.md',
        },
        'records': records,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    p = os.path.join(REPORTS_DIR, 'optimize_compare.json')
    save_json(out, p)
    print()
    print(f'  汇总: {p}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
