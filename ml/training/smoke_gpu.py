# -*- coding: utf-8 -*-
"""GPU 端到端冒烟测试 —— 验证 ResNet18 能否真正在 RTX 4060 上训练

目的：在正式训练前，用极小规模确认整条链路（数据 → 模型 → 前向 → 反向 → 更新）
      在 GPU 上无异常，并实测速度以估算完整训练耗时。

不做真训练，只跑 30 个 batch 看吞吐。
"""

import os
import sys
import time

import torch
import torch.nn as nn

_HERE = os.path.dirname(os.path.abspath(__file__))
_ML = os.path.dirname(_HERE)
sys.path.insert(0, _ML)
sys.path.insert(0, os.path.join(_ML, 'dataset'))

from config import TrainConfig, device_summary, ensure_dirs  # noqa: E402
from fish_dataset import build_loaders, load_split, make_class_weights  # noqa: E402
from train import build_model, build_scheduler, param_groups, confusion_matrix, metrics_from_cm  # noqa: E402


def main() -> int:
    ensure_dirs()
    cfg = TrainConfig()
    cfg.num_workers = 4
    device = torch.device('cuda')

    print('=' * 76)
    print('GPU 端到端冒烟测试')
    print('=' * 76)
    print(f'  {device_summary()}')
    print()

    torch.manual_seed(cfg.seed)

    print('  [1/5] 构建数据加载器')
    dl_train, dl_val, dl_test = build_loaders(cfg)
    print()

    print('  [2/5] 构建模型')
    model = build_model(cfg).to(device)
    n_param = sum(p.numel() for p in model.parameters())
    print(f'        ResNet18 参数 {n_param:,}')
    # 显存占用
    torch.cuda.reset_peak_memory_stats()
    print(f'        模型上卡后显存 {torch.cuda.memory_allocated()/1024**2:.1f} MB')
    print()

    print('  [3/5] 损失与优化器')
    split = load_split()
    class_w = make_class_weights(split['train'], cfg.num_classes, cfg.class_weight_power)
    criterion = nn.CrossEntropyLoss(weight=class_w.to(device),
                                    label_smoothing=cfg.label_smoothing)
    optimizer = torch.optim.Adam(param_groups(model, cfg), weight_decay=cfg.weight_decay)
    scheduler = build_scheduler(optimizer, cfg, len(dl_train))
    print(f'        类别权重范围 {class_w[class_w>0].min():.2f} ~ {class_w.max():.2f}')
    print()

    print('  [4/5] 前向 + 反向 + 更新（30 batch，bf16 AMP）')
    model.train()
    N = 30
    t0 = time.time()
    total_loss, n = 0.0, 0
    amp_dtype = torch.bfloat16

    for bi, (xb, yb) in enumerate(dl_train):
        if bi >= N:
            break
        xb = xb.to(device, non_blocking=True)
        yb = yb.to(device, non_blocking=True)
        with torch.autocast(device_type='cuda', dtype=amp_dtype):
            logits = model(xb)
            loss = criterion(logits, yb)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()
        scheduler.step()
        total_loss += loss.item() * yb.size(0)
        n += yb.size(0)
        if bi == 0:
            print(f'        首批 loss={loss.item():.4f}（初始应约 ln(23)={torch.log(torch.tensor(23.0)):.3f}）')

    torch.cuda.synchronize()
    dt = time.time() - t0
    bs = cfg.batch_size
    imgs_per_s = n / dt
    print(f'        处理 {n} 张耗时 {dt:.2f}s → {imgs_per_s:.0f} 张/秒')
    print(f'        平均 loss {total_loss/n:.4f}')
    print(f'        峰值显存 {torch.cuda.max_memory_allocated()/1024**3:.2f} GB / 8.00 GB')
    print()

    # 估算完整训练
    n_train = len(dl_train.dataset)
    per_epoch = n_train / imgs_per_s
    print(f'  [5/5] 耗时估算')
    print(f'        训练集 {n_train:,} 张')
    print(f'        每轮约 {per_epoch:.0f} 秒 = {per_epoch/60:.1f} 分钟')
    for ep in (10, 20, 30):
        print(f'        {ep:2d} 轮约 {per_epoch*ep/60:.0f} 分钟')
    print()

    print('  ✓ GPU 链路全部打通')
    return 0


if __name__ == '__main__':
    sys.exit(main())
