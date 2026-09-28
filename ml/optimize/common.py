# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · M3.5 模型优化 —— 公共设施

统一口径（保证「优化前 / 优化后」在同一把尺子上比较，PRD §7.5 复测要求）：
  1. 模型结构一律来自 ml/training/train.py 的 build_model()，不另写第二份；
  2. 评估数据一律来自 ml/dataset/fish_dataset 的 test 划分（split.json 已冻结），
     且使用 preprocess.build_eval_transform() 的确定性预处理（无任何随机性）；
  3. 指标算法一律来自 ml/training/train.py 的 metrics_from_cm()，与训练期同源。

因此本模块不引入任何新的模型定义、新的预处理口径或新的指标算法 —— 只做优化与测量。
"""

import io
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
ML = os.path.join(ROOT, 'ml')
for _p in (ML, os.path.join(ML, 'dataset'), os.path.join(ML, 'training'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from config import (  # noqa: E402
    MODELS_DIR, REPORTS_DIR, TrainConfig, device_summary, ensure_dirs, pick_device,
)
from fish_dataset import FishDataset, load_split  # noqa: E402
from preprocess import build_eval_transform  # noqa: E402
from species_meta import INDEX_TO_CN, INDEX_TO_SCI, NUM_CLASSES  # noqa: E402
from train import build_model, confusion_matrix, metrics_from_cm  # noqa: E402

BASELINE_CKPT = os.path.join(MODELS_DIR, 'M1_main_224', 'best.pt')
TEST_BATCH = 64

DEVICE_GPU = 'cuda'
DEVICE_CPU = 'cpu'


# ---------------- 模型加载 ----------------

def load_ckpt(path: str = BASELINE_CKPT) -> dict:
    return torch.load(path, map_location='cpu', weights_only=False)


def baseline_config(ckpt: dict) -> TrainConfig:
    """从 checkpoint 内嵌 config 还原训练配置，保证结构完全一致。

    pretrained 强制置 False —— 权重来自 ckpt，不需要也不应触发 ImageNet 权重下载。
    """
    cfg = TrainConfig()
    raw = ckpt.get('config') or {}
    for k, v in raw.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    cfg.pretrained = False
    return cfg


def load_baseline(path: str = BASELINE_CKPT):
    """返回 (model.eval(), cfg, ckpt)。"""
    ckpt = load_ckpt(path)
    cfg = baseline_config(ckpt)
    model = build_model(cfg)
    model.load_state_dict(ckpt['state_dict'], strict=True)
    return model.eval(), cfg, ckpt


# ---------------- FX 静态量化模型的往返 ----------------

FX_EXAMPLE_SHAPE = (1, 3, 224, 224)


def rebuild_static_int8_fx(base_model, state_path: str | None = None,
                           example_shape: tuple = FX_EXAMPLE_SHAPE,
                           backend: str = 'x86'):
    """按同样配方重建 FX 静态量化结构，并可灌入已保存的 state_dict。

    【为什么不用 torch.save(整模块)】
    FX GraphModule 走 pickle 反序列化时会重新 trace，而量化融合后的算子
    （ConvReLU2d / ConvBnReLU2d 等）在该路径下缺少 `_modules` 属性，实测报错：
        AttributeError: 'ConvReLU2d' object has no attribute '_modules'
    所以 int8 FX 模型不能整模块往返 —— 这不是配置问题，是序列化机制的固有限制。

    【本函数采用的方案】state_dict + 重建配方：
      prepare_fx（结构由 qconfig 与模型拓扑决定，与校准数据无关）
      → 用固定随机数据跑 2 批使 observer 产生合法统计（仅为了让 convert_fx 不报错）
      → convert_fx 固化结构
      → load_state_dict 覆盖全部量化参数（scale/zero_point 都是 buffer，会被完整恢复）
    这样得到的仍是标准 nn.Module，评估与耗时测量代码无需任何特判。

    round-trip 正确性由 quantize.py 落盘时的自检断言保证。
    """
    import copy
    from torch.ao.quantization import get_default_qconfig_mapping
    from torch.ao.quantization.quantize_fx import convert_fx, prepare_fx

    m = copy.deepcopy(base_model).eval()
    qmap = get_default_qconfig_mapping(backend)
    example = (torch.randn(*example_shape),)
    prepared = prepare_fx(m, qmap, example)

    with torch.inference_mode():
        for _ in range(2):
            prepared(torch.randn(*example_shape))

    converted = convert_fx(prepared).eval()
    if state_path:
        sd = torch.load(state_path, map_location='cpu', weights_only=False)
        converted.load_state_dict(sd, strict=True)
    return converted.eval()


# ---------------- 测试集（冻结口径） ----------------

def make_test_loader(batch_size: int = TEST_BATCH, num_workers: int = 0) -> DataLoader:
    split = load_split()
    ds = FishDataset(split['test'], build_eval_transform())
    return DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)


def test_set_size() -> int:
    return len(load_split()['test'])


# ---------------- 评估 ----------------

def evaluate(model, device: str = DEVICE_CPU, batch_size: int = TEST_BATCH,
             num_workers: int = 0) -> tuple[dict, np.ndarray, float]:
    """在冻结测试集上完整评估。

    device 必须与模型实际可运行的设备一致：int8 量化模型只支持 CPU，
    传入 'cuda' 会抛错 —— 这是设计使然，不要 try/except 掩盖。
    """
    model.eval()
    is_quant = is_quantized(model)
    if is_quant and device != DEVICE_CPU:
        raise ValueError('int8 量化模型只能在本机 CPU 上推理，请传 device="cpu"')
    model = model.to(device)

    dl = make_test_loader(batch_size, num_workers)
    preds, labels = [], []
    t0 = time.perf_counter()
    with torch.inference_mode():
        for xb, yb in dl:
            logits = model(xb.to(device))
            preds.append(logits.argmax(1).cpu().numpy())
            labels.append(yb.numpy())
    seconds = time.perf_counter() - t0

    y_pred = np.concatenate(preds)
    y_true = np.concatenate(labels)
    cm = confusion_matrix(y_pred, y_true, NUM_CLASSES)
    m = metrics_from_cm(cm)
    m['eval_seconds'] = round(seconds, 2)
    m['eval_device'] = device
    m['eval_n'] = int(cm.sum())
    return m, cm, seconds


# ---------------- 耗时基准 ----------------

def bench_forward(model, device: str = DEVICE_CPU, n_warm: int = 10, n_rep: int = 50,
                  batch_size: int = 1) -> dict:
    """纯前向耗时基准（batch=1）。返回 p50 / min / max，单位 ms。

    预热是必须的：CUDA kernel 首次启动、量化算子的首次打包都会污染首轮计时。
    """
    model.eval()
    if is_quantized(model) and device != DEVICE_CPU:
        raise ValueError('int8 量化模型只能在 CPU 上推理')
    model = model.to(device)
    x = torch.randn(batch_size, 3, 224, 224, device=device)

    with torch.inference_mode():
        for _ in range(n_warm):
            model(x)
        sync(device)
        ts = []
        for _ in range(n_rep):
            t0 = time.perf_counter()
            model(x)
            sync(device)
            ts.append((time.perf_counter() - t0) * 1000.0)

    ts.sort()
    return {
        'device': device,
        'batch_size': batch_size,
        'p50_ms': round(ts[len(ts) // 2], 3),
        'min_ms': round(ts[0], 3),
        'max_ms': round(ts[-1], 3),
        'mean_ms': round(sum(ts) / len(ts), 3),
        'n_rep': n_rep,
    }


def sync(device: str) -> None:
    if device.startswith('cuda') and torch.cuda.is_available():
        torch.cuda.synchronize()


# ---------------- 体积测量 ----------------

def is_quantized(model) -> bool:
    for m in model.modules():
        if isinstance(m, (torch.ao.nn.quantized.dynamic.Linear,
                          torch.ao.nn.quantized.Linear,
                          torch.ao.nn.quantized.Conv2d,
                          torch.ao.nn.quantized.dynamic.LSTM)):
            return True
        if type(m).__module__.startswith('torch.ao.nn.quantized'):
            return True
    return False


def serialized_bytes(model) -> int:
    """序列化后的真实字节数（含 pickle 开销），用于体积对照。

    统一口径：所有模型都走 torch.save(obj) 到内存缓冲测量，
    避免「浮点模型测 state_dict / 量化模型测整模块」造成的不公平比较。
    """
    buf = io.BytesIO()
    torch.save(model, buf)
    return buf.getbuffer().nbytes


def param_count(model) -> int:
    try:
        return sum(p.numel() for p in model.parameters())
    except Exception:
        return -1


def count_conv_linear_channels(model) -> dict:
    """统计 Conv2d / Linear 的输入输出通道明细，用于剪枝前后结构对照。"""
    convs, lins = [], []
    for name, mod in model.named_modules():
        if isinstance(mod, nn.Conv2d):
            convs.append({
                'name': name, 'in': mod.in_channels, 'out': mod.out_channels,
                'k': mod.kernel_size[0], 'stride': mod.stride[0],
                'params': mod.weight.numel(),
            })
        elif isinstance(mod, nn.Linear):
            lins.append({
                'name': name, 'in': mod.in_features, 'out': mod.out_features,
                'params': mod.weight.numel(),
            })
    return {'conv': convs, 'linear': lins,
            'conv_total_params': sum(c['params'] for c in convs),
            'linear_total_params': sum(l['params'] for l in lins)}


# ---------------- 落盘 ----------------

def save_json(obj: dict, path: str) -> str:
    ensure_dirs()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


def model_dir(name: str) -> str:
    d = os.path.join(MODELS_DIR, name)
    os.makedirs(d, exist_ok=True)
    return d


def dump(obj, path: str):
    torch.save(obj, path)
    return path


if __name__ == '__main__':
    ensure_dirs()
    print('=' * 74)
    print(' M3.5 公共设施自检')
    print('=' * 74)
    print(f'  {device_summary()}')
    print(f'  基线权重        : {BASELINE_CKPT}')
    print(f'  测试集样本数    : {test_set_size():,}')
    m, cfg, ckpt = load_baseline()
    print(f'  参数量          : {param_count(m):,}')
    print(f'  序列化体积      : {serialized_bytes(m)/1024**2:.2f} MB')
    print(f'  是否量化        : {is_quantized(m)}')
    print()
    print('  结构明细（前 8 个 conv）...')
    info = count_conv_linear_channels(m)
    for c in info['conv'][:8]:
        print(f'    {c["name"]:34s} in={c["in"]:4d} out={c["out"]:4d} k={c["k"]}')
    print(f'  conv 参数量 {info["conv_total_params"]:,} / linear {info["linear_total_params"]:,}')
    print()
    print('  ✓ 自检通过')
