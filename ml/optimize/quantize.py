# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · M3.5 量化实验

对应 PRD §7.5 的优化手段之一：

    | 动态量化 | 对全连接层执行 int8 动态量化 | GPU 环境单图耗时超过目标，或需在 CPU 环境部署 |

本脚本实现两条量化路径并给出实测对照：

  A. 动态量化（PRD 原文方案）
     torch.ao.quantization.quantize_dynamic(model, {nn.Linear}, dtype=qint8)
     —— 严格按 PRD 措辞，只作用于全连接层。

  B. FX 静态量化（补充方案，超出 PRD §7.5 列举范围，供裁决）
     quantize_fx.prepare_fx/convert_fx + x86 qconfig
     —— 对 Conv + Linear 一并 int8 化，是真正能在 CPU 上降耗时的路径。
        之所以要做：PRD §7.5 把「需在 CPU 环境部署」列为启用条件，
        而项目本身有「显存不足降级 CPU 推理」的需求（§7.6.1 设备策略），
        因此 CPU 侧加速具有实际业务含义，需实测数据支撑是否采纳。

重要事实（决定 A 的收益上限）：
  ResNet18 的参数量 99.81% 在卷积层，全连接层仅 11,776 参数（0.11%）。
  因此「只量化全连接层」的加速空间天然极小 —— 这一步必须用数据说话，不能靠推测。

标定数据纪律：静态量化的校准集使用 **val 划分**，不使用 test 划分
（与 PRD §7.4.3 阈值标定"不使用测试集"同一纪律）。

用法：
    python ml/optimize/quantize.py --mode both
    python ml/optimize/quantize.py --mode dynamic --skip-eval
"""

import argparse
import copy
import os
import sys
import time

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from common import (  # noqa: E402
    BASELINE_CKPT, DEVICE_CPU, REPORTS_DIR, bench_forward,
    count_conv_linear_channels, ensure_dirs, evaluate, is_quantized,
    load_baseline, load_split, model_dir, param_count, rebuild_static_int8_fx,
    save_json, serialized_bytes, test_set_size,
)
from fish_dataset import FishDataset  # noqa: E402
from preprocess import build_eval_transform  # noqa: E402


def make_val_loader(batch_size: int = 32, num_workers: int = 0) -> DataLoader:
    """校准集：val 划分 + 确定性预处理（不使用 test）。"""
    split = load_split()
    ds = FishDataset(split['val'], build_eval_transform())
    return DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)


# ---------------- 路径 A：动态量化 ----------------

def build_dynamic_int8(model: nn.Module) -> nn.Module:
    """对全连接层做 int8 动态量化（PRD §7.5 原文方案）。

    动态量化的含义：权重离线量化为 int8，激活在推理时按批动态量化。
    它只替换 Linear / LSTM 等算子，卷积层保持不变。
    """
    q = torch.ao.quantization.quantize_dynamic(
        copy.deepcopy(model).eval(),
        {nn.Linear},
        dtype=torch.qint8,
        inplace=False,
    )
    return q.eval()


# ---------------- 路径 B：FX 静态量化 ----------------

def build_static_int8_fx(model: nn.Module, calib_loader: DataLoader,
                         n_calib_batches: int = 16) -> tuple[nn.Module, dict]:
    """对 Conv + Linear 做 int8 静态量化（x86 后端），返回 (模型, 校准信息)。

    流程：prepare_fx（插入观察点并做算子融合） → 校准 → convert_fx（固化 int8）。
    校准集用 val 划分。
    """
    from torch.ao.quantization import get_default_qconfig_mapping
    from torch.ao.quantization.quantize_fx import convert_fx, prepare_fx

    example = (torch.randn(1, 3, 224, 224),)
    qconfig_mapping = get_default_qconfig_mapping('x86')

    m = copy.deepcopy(model).eval()
    prepared = prepare_fx(m, qconfig_mapping, example)

    n_seen = 0
    t0 = time.perf_counter()
    with torch.inference_mode():
        for bi, (xb, _) in enumerate(calib_loader):
            if bi >= n_calib_batches:
                break
            prepared(xb)
            n_seen += xb.size(0)
    calib_s = round(time.perf_counter() - t0, 2)

    converted = convert_fx(prepared).eval()
    info = {
        'backend': 'x86',
        'calib_split': 'val',
        'calib_batches': min(n_calib_batches, len(calib_loader)),
        'calib_images': n_seen,
        'calib_seconds': calib_s,
    }
    return converted, info


# ---------------- 单条路径的完整测量 ----------------

def measure(name: str, model, method: str, extra: dict, *, skip_eval: bool,
            saver=None) -> dict:
    """产出体积 + 耗时 + （可选）测试集精度，落盘模型与 meta。

    saver(d) -> (model_path, size_mb)：自定义落盘方式。
    默认整模块 torch.save；FX 静态量化必须改用 state_dict（原因见
    common.rebuild_static_int8_fx 的 docstring：整模块 pickle 往返会报
    `'ConvReLU2d' object has no attribute '_modules'`）。
    """
    d = model_dir(name)
    if saver is None:
        model_path = os.path.join(d, 'model.pt')
        torch.save(model, model_path)
        size_mb = serialized_bytes(model) / 1024 ** 2
        save_mode = 'module'
    else:
        model_path, size_mb = saver(d)
        save_mode = 'state_dict'

    cpu_bench = bench_forward(model, DEVICE_CPU)
    rec = {
        'name': name,
        'method': method,
        'source_ckpt': BASELINE_CKPT,
        'save_mode': save_mode,
        'is_quantized': is_quantized(model),
        'param_count': param_count(model),
        'serialized_mb': round(size_mb, 3),
        'bench_cpu_ms': cpu_bench,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    rec.update(extra)

    if not skip_eval:
        m, cm, sec = evaluate(model, DEVICE_CPU)
        rec['test_metrics'] = m
        rec['test_eval_seconds_cpu'] = round(sec, 1)

    rec['model_path'] = model_path
    rec['file_mb_on_disk'] = round(os.path.getsize(model_path) / 1024 ** 2, 3)
    save_json(rec, os.path.join(d, 'meta.json'))

    print(f'  ✓ {name}')
    print(f'      体积({save_mode}) {rec["serialized_mb"]:.3f} MB  |  '
          f'磁盘 {rec["file_mb_on_disk"]:.3f} MB')
    print(f'      CPU 前向 p50 {cpu_bench["p50_ms"]:.3f} ms (min {cpu_bench["min_ms"]:.3f} / '
          f'max {cpu_bench["max_ms"]:.3f})')
    if 'test_metrics' in rec:
        tm = rec['test_metrics']
        print(f'      测试集 acc {tm["accuracy"]:.6f}  macroF1 {tm["macro_f1"]:.6f}  '
              f'加权F1 {tm["weighted_f1"]:.6f}  ({rec["test_eval_seconds_cpu"]}s)')
    print(f'      → {model_path}')
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['dynamic', 'static', 'both'], default='both')
    ap.add_argument('--calib-batches', type=int, default=16)
    ap.add_argument('--calib-batch-size', type=int, default=32)
    ap.add_argument('--skip-eval', action='store_true', help='跳过测试集评估（仅测体积与耗时）')
    args = ap.parse_args()

    ensure_dirs()
    print('=' * 78)
    print(' 海瞳鱼鉴 · M3.5 量化实验')
    print('=' * 78)

    model, cfg, ckpt = load_baseline()
    print(f'  基线: {BASELINE_CKPT}')
    print(f'    参数量 {param_count(model):,}  体积(序列化) '
          f'{serialized_bytes(model)/1024**2:.3f} MB')
    info = count_conv_linear_channels(model)
    print(f'    conv 参数 {info["conv_total_params"]:,} / linear 参数 '
          f'{info["linear_total_params"]:,}  '
          f'(linear 占比 {info["linear_total_params"]/param_count(model)*100:.3f}%)')
    print(f'    测试集 {test_set_size():,} 张')
    print()

    results = {}

    if args.mode in ('dynamic', 'both'):
        print('-' * 78)
        print(' 路径 A · 动态量化（仅全连接层 int8，PRD §7.5 原文方案）')
        print('-' * 78)
        q = build_dynamic_int8(model)
        nq = sum(1 for m in q.modules() if isinstance(m, torch.ao.nn.quantized.dynamic.Linear))
        print(f'  已量化 Linear 模块数: {nq}')
        results['dynamic'] = measure(
            'M1_main_224_dynamic_int8', q, 'dynamic_int8_linear',
            {'target': 'nn.Linear', 'quantized_linear_modules': nq,
             'note': 'PRD §7.5 原文方案；ResNet18 的 linear 仅占总参数 0.11%'},
            skip_eval=args.skip_eval)
        print()

    if args.mode in ('static', 'both'):
        print('-' * 78)
        print(' 路径 B · FX 静态量化（Conv + Linear int8，补充方案）')
        print('-' * 78)
        val_loader = make_val_loader(args.calib_batch_size)
        q2, calib = build_static_int8_fx(model, val_loader, args.calib_batches)
        print(f'  校准: {calib["calib_images"]} 张 (val 划分, {calib["calib_seconds"]}s)')
        nqc = sum(1 for m in q2.modules()
                  if type(m).__module__.startswith('torch.ao.nn.quantized')
                  and not type(m).__module__.endswith('dynamic'))
        print(f'  已量化模块数: {nqc}')

        def _save_fx_static(d):
            """FX 量化模型只能以 state_dict 分发（整模块 pickle 往返会失败）。"""
            p = os.path.join(d, 'state_dict.pt')
            torch.save(q2.state_dict(), p)
            return p, os.path.getsize(p) / 1024 ** 2

        rec = measure(
            'M1_main_224_static_int8', q2, 'static_int8_fx_x86',
            {'calibration': calib, 'quantized_modules': nqc,
             'rebuild_recipe': {'backend': 'x86', 'example_shape': [1, 3, 224, 224],
                                'rebuild_fn': 'common.rebuild_static_int8_fx'},
             'note': '补充方案，超出 PRD §7.5 列举；针对「CPU 降级部署」场景'},
            skip_eval=args.skip_eval, saver=_save_fx_static)

        # round-trip 自检：落盘的 state_dict 必须能完整还原同一模型。
        # 没有这一步，就只是"写了个文件"，并不知道它能不能用。
        probe = torch.randn(4, 3, 224, 224)
        with torch.inference_mode():
            ref = q2(probe)
            rt = rebuild_static_int8_fx(model, state_path=rec['model_path'])
            diff = float((ref - rt(probe)).abs().max())
        rec['roundtrip_max_abs_diff'] = diff
        rec['roundtrip_ok'] = diff < 1e-6
        save_json(rec, os.path.join(model_dir('M1_main_224_static_int8'), 'meta.json'))
        print(f'      round-trip 自检: 最大绝对差 {diff:.3e} → '
              f'{"PASS" if rec["roundtrip_ok"] else "FAIL"}')
        results['static'] = rec
        print()

    out = os.path.join(REPORTS_DIR, 'optimize_quantize.json')
    save_json({'baseline_ckpt': BASELINE_CKPT, 'results': results,
               'args': vars(args),
               'created_at': time.strftime('%Y-%m-%d %H:%M:%S')}, out)
    print(f'  汇总: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
