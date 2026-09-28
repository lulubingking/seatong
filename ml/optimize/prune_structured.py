# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · M3.5 结构化剪枝实验

对应 PRD §7.5 的优化手段之一：

    | 结构化剪枝 | 按通道重要性剪枝，稀疏度不超过 30% | 模型体积或加载时间成为瓶颈 |

实现要点（与"掩码式剪枝"的关键区别）：

  torch.nn.utils.prune 的系列 API 是**掩码式**剪枝 —— 把权重置零，但张量形状不变，
  因此 **参数量、计算量、模型体积都不会下降**，还会额外增加 mask buffer 使体积变大。
  这对本项目毫无意义（PRD 的启用条件是"模型体积成为瓶颈"）。

  故本脚本实现**真正的结构化通道剪枝**（Network Slimming 思路）：
    1. 以每个 BasicBlock 输出端 BatchNorm 的缩放因子 γ = bn2.weight 的绝对值作为通道重要性；
    2. 按重要性升序剪掉每个 block 输出通道的一定比例（有下限保护，防止层被剪空）；
    3. **重建网络**：同步缩减 conv2 的 out_channels、bn2、shortcut（conv1x1+bn）的输出通道，
       以及下一个 block 的 conv1.in_channels；末端同步缩减 fc.in_features。
       —— 这样参数量、FLOPs、模型体积才真正下降；
    4. 剪枝必然损伤精度，随后在训练集上微调、以**验证集**宏观 F1 选最优权重。

不剪的层与原因：
  · conv1 / bn1（输入是图像，剪它等于裁剪输入通道，没有意义）；
  · layer1.0 的输出通道 —— 它的 shortcut 是恒等映射（无 downsample）。
    一旦剪掉它的输出通道，恒等映射维度就不再匹配，必须**新增**一个 1×1 卷积 shortcut，
    这等于改变网络拓扑而非剪枝。故 layer1.0 保持 64 通道不动，从 layer1.1 起剪。

标定纪律：剪枝比例由 PRD 给定（≤30%），不依赖任何数据划分；
微调用 train 划分，选权重用 val 划分，**test 划分留到最终复测**（compare.py）一次性使用。

用法：
    python ml/optimize/prune_structured.py --ratio 0.30 --ft-epochs 8
    python ml/optimize/prune_structured.py --ratio 0.15 --ft-epochs 6 --dry-run
"""

import argparse
import copy
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from torch.optim import Adam

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from common import (  # noqa: E402
    BASELINE_CKPT, DEVICE_CPU, DEVICE_GPU, REPORTS_DIR, bench_forward,
    count_conv_linear_channels, ensure_dirs, evaluate, load_baseline,
    model_dir, param_count, pick_device, save_json, serialized_bytes,
)
from fish_dataset import build_loaders, load_split, make_class_weights  # noqa: E402
from species_meta import INDEX_TO_CN, INDEX_TO_SCI  # noqa: E402
from train import build_scheduler, confusion_matrix, metrics_from_cm, param_groups, run_epoch  # noqa: E402

FEATURES = 64   # conv1 输出通道数（ResNet18 固定）

# 四个 stage：(名称, block 数, 输出通道数)。
#
# 【关键设计】剪枝单元取「stage」而非「单个 block」：
#   残差结构要求同一 stage 内所有 block 的输出通道必须是**同一个集合**
#   （out = conv2_out + identity 需逐元素相加）。若按 block 各自剪枝，
#   无 downsample 的 block 的恒等映射就会维度错配 —— 实测报错为
#   `RuntimeError: The size of tensor a (45) must match the size of tensor b (64)`。
#   故每个 stage 选定一个共同保留集 A：stage 内恒等映射自动成立，
#   **无需插入任何新模块、不改变网络拓扑**，是无损的通道剪枝。
STAGES = [
    ('layer1', 2, 64),
    ('layer2', 2, 128),
    ('layer3', 2, 256),
    ('layer4', 2, 512),
]


# ---------------- 子模块访问与切片 ----------------

def walk(root, dotted: str):
    """按点名访问子模块。'layer2.0.conv1' → root.layer2[0].conv1"""
    cur = root
    for part in dotted.split('.'):
        if part.isdigit() and isinstance(cur, (nn.Sequential, nn.ModuleList)):
            cur = cur[int(part)]
        else:
            cur = getattr(cur, part)
    return cur


def slice_bn(bn: nn.BatchNorm2d, idx: list[int]) -> nn.BatchNorm2d:
    """按索引切出新的 BatchNorm2d，统计量一并切片（否则归一层语义会漂移）。"""
    new = nn.BatchNorm2d(
        len(idx), eps=bn.eps, momentum=bn.momentum,
        affine=bn.affine, track_running_stats=bn.track_running_stats,
    )
    if bn.affine:
        new.weight.data = bn.weight.data[idx].clone()
        new.bias.data = bn.bias.data[idx].clone()
    if bn.track_running_stats:
        new.running_mean.data = bn.running_mean.data[idx].clone()
        new.running_var.data = bn.running_var.data[idx].clone()
        new.num_batches_tracked.data = bn.num_batches_tracked.data.clone()
    return new


# ---------------- 通道选择 ----------------

def select_channels(model, ratio: float, min_keep_ratio: float = 0.40,
                    protect_first_layer: bool = False,
                    verbose: bool = True) -> tuple[dict, dict]:
    """按 bn2 的 |γ| 为每个 stage 选定**共同**保留通道集。

    重要性度量：同一 stage 内各 block 的 bn2 缩放因子 |γ|，
    先各自按均值归一化（不同 stage 的 γ 量级差异可达 10 倍），再取平均。
    求平均而非取最小，是因为两个 block 的输出处于同一残差通道空间，
    通道 j 要"存活"必须在两处都不被淘汰，用均值是温和折中。

    protect_first_layer=True 时 stage1 保持全通道不剪。此时 stem（conv1/bn1）
    也无需缩减 —— 因为 layer1.0 的恒等映射输入（64）与输出（64）天然一致。
    该开关用于对照"剪第一层是否得不偿失"。

    返回 (keep_map, report)；keep_map 的键为 stage 名。
    """
    keep_map, rows = {}, []
    total_channels = pruned_channels = 0

    for stage, n_blocks, planes in STAGES:
        if protect_first_layer and stage == 'layer1':
            keep_map[stage] = list(range(planes))
            rows.append({
                'stage': stage, 'blocks': n_blocks, 'channels': planes,
                'kept': planes, 'pruned': 0, 'prune_rate': 0.0,
                'skipped': 'protect_first_layer',
                'per_block_gamma_mean': [],
            })
            continue

        score, per_block = None, []
        for bi in range(n_blocks):
            bn = walk(model, f'{stage}.{bi}.bn2')
            g = bn.weight.detach().abs().cpu().numpy().astype(np.float64)
            per_block.append(g)
            norm = g / max(float(g.mean()), 1e-12)
            score = norm if score is None else score + norm
        score = score / n_blocks

        c = planes
        k = int(round(c * ratio))
        k = max(0, min(k, c - max(1, int(round(c * min_keep_ratio)))))
        # 稳定排序 + 原索引升序回排，保留通道在通道维上仍有序（利于推理访存连续性）
        order = np.argsort(score, kind='stable')
        drop = set(order[:k].tolist())
        kept = [i for i in range(c) if i not in drop]

        keep_map[stage] = kept
        total_channels += c
        pruned_channels += k
        rows.append({
            'stage': stage, 'blocks': n_blocks, 'channels': c,
            'kept': len(kept), 'pruned': k, 'prune_rate': round(k / c, 4),
            'score_min_kept': round(float(score[kept].min()), 6) if kept else None,
            'score_max_dropped': round(float(score[order[k - 1]]), 6) if k > 0 else None,
            'per_block_gamma_mean': [round(float(g.mean()), 6) for g in per_block],
        })

    report = {
        'requested_ratio': ratio,
        'min_keep_ratio': min_keep_ratio,
        'protect_first_layer': protect_first_layer,
        'stem_pruned': len(keep_map.get('layer1', [])) not in (0, FEATURES),
        'prunable_channels': total_channels,
        'pruned_channels': pruned_channels,
        'actual_sparsity': round(pruned_channels / total_channels, 4) if total_channels else 0.0,
        'per_stage': rows,
    }

    if verbose:
        print('  通道重要性：bn2 的 |γ|（Network Slimming 口径），按 stage 取均值')
        if protect_first_layer:
            print('  ! 已启用保护首层：stage1 与 stem 保持全通道')
        print(f'  {"stage":8s} {"原通道":>7s} {"保留":>6s} {"剪掉":>6s} {"比例":>7s} '
              f'{"score最小(保留)":>16s} {"score最大(剪掉)":>16s}  γ均值(各block)')
        for r in rows:
            g = ', '.join(f'{x:.3f}' for x in r.get('per_block_gamma_mean', [])) or '—'
            if r.get('skipped'):
                print(f'  {r["stage"]:8s} {r["channels"]:7d} {r["kept"]:6d} {r["pruned"]:6d} '
                      f'{"—":>7s} {"—":>16s} {"—":>16s}  [{g}]  (跳过)')
                continue
            print(f'  {r["stage"]:8s} {r["channels"]:7d} {r["kept"]:6d} {r["pruned"]:6d} '
                  f'{r["prune_rate"]:7.2%} {r["score_min_kept"]:16.6f} '
                  f'{(r["score_max_dropped"] or 0):16.6f}  [{g}]')
        print(f'  可剪通道总数 {total_channels:,} / 实剪 {pruned_channels:,} '
              f'→ 实际稀疏度 {report["actual_sparsity"]:.2%}')
        if report['stem_pruned']:
            print(f'  ! stem（conv1/bn1）输出同步缩减，否则 layer1.0 的恒等映射维度错配')

    return keep_map, report


# ---------------- 结构重建 ----------------

def rebuild_with_channels(model: nn.Module, keep_map: dict) -> nn.Module:
    """按 keep_map（stage → 保留通道索引）重建一个真正变瘦的模型并迁移权重。

    每个 block 必须同步处理的四处（漏一处就 forward 报维度错）：
      0. **stem（conv1/bn1）输出通道** ← 当 stage1 被剪时，必须同步缩减。
         否则 layer1.0 的恒等映射是 64→64 而 conv2 输出只有 45，直接报
         `The size of tensor a (45) must match the size of tensor b (64)`。
         （此坑已实测踩中两次，第二次的根因就在这里。）
      1. conv1.in_channels  ← 本 block 的输入通道
         （stage 第一个 block 取上一个 stage 的保留集，其余取本 stage 的保留集）
      2. conv2.out_channels / bn2  ← 本 stage 的保留集
      3. downsample（若存在，只出现在 stage 第一个 block）：conv1×1 的 in/out 与 bn 同步
      4. 末尾 fc.in_features ← 最后一个 stage 的保留集

    stage 内其余 block 的恒等映射**无需任何处理** —— 因为本 stage 内所有 block
    共用同一保留集，输入与输出通道数天然一致。这正是按 stage 剪枝相比
    按 block 剪枝的关键优势。
    """
    m = copy.deepcopy(model)
    a1 = keep_map.get('layer1', list(range(FEATURES)))

    if len(a1) != FEATURES:
        old_c1, old_b1 = m.conv1, m.bn1
        new_c1 = nn.Conv2d(old_c1.in_channels, len(a1), kernel_size=old_c1.kernel_size,
                           stride=old_c1.stride, padding=old_c1.padding, bias=False)
        new_c1.weight.data = old_c1.weight.data[a1].clone()
        m.conv1 = new_c1
        m.bn1 = slice_bn(old_b1, a1)

    prev = a1

    for stage, n_blocks, planes in STAGES:
        cur = keep_map.get(stage, list(range(planes)))
        for bi in range(n_blocks):
            block = walk(m, f'{stage}.{bi}')
            src = prev if bi == 0 else cur      # conv1 的输入来源
            old_conv1, old_conv2 = block.conv1, block.conv2

            new_conv1 = nn.Conv2d(len(src), planes, kernel_size=3,
                                  stride=old_conv1.stride, padding=old_conv1.padding,
                                  bias=False)
            new_conv1.weight.data = old_conv1.weight.data[:, src].clone()
            setattr(block, 'conv1', new_conv1)

            new_conv2 = nn.Conv2d(planes, len(cur), kernel_size=3,
                                  stride=old_conv2.stride, padding=old_conv2.padding,
                                  bias=False)
            new_conv2.weight.data = old_conv2.weight.data[cur].clone()
            setattr(block, 'conv2', new_conv2)

            setattr(block, 'bn2', slice_bn(block.bn2, cur))

            if block.downsample is not None:
                oc, ob = block.downsample[0], block.downsample[1]
                new_oc = nn.Conv2d(len(prev), len(cur), kernel_size=1,
                                   stride=oc.stride, padding=oc.padding, bias=False)
                new_oc.weight.data = oc.weight.data[cur][:, prev].clone()
                block.downsample[0] = new_oc
                block.downsample[1] = slice_bn(ob, cur)

        prev = cur

    fc = m.fc
    if isinstance(fc, nn.Sequential):
        lin = fc[1]
        new_lin = nn.Linear(len(prev), lin.out_features, bias=lin.bias is not None)
        new_lin.weight.data = lin.weight.data[:, prev].clone()
        if lin.bias is not None:
            new_lin.bias.data = lin.bias.data.clone()
        fc[1] = new_lin
    else:
        new_lin = nn.Linear(len(prev), fc.out_features, bias=fc.bias is not None)
        new_lin.weight.data = fc.weight.data[:, prev].clone()
        if fc.bias is not None:
            new_lin.bias.data = fc.bias.data.clone()
        m.fc = new_lin

    return m.eval()


# ---------------- 验证集评估（微调选权重用，不动 test） ----------------

def eval_on_val(model, cfg, device: str, batch_size: int = 64) -> dict:
    from torch.utils.data import DataLoader
    from fish_dataset import FishDataset
    from preprocess import build_eval_transform

    split = load_split()
    ds = FishDataset(split['val'], build_eval_transform())
    dl = DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=0)
    model.eval().to(device)
    preds, labels = [], []
    with torch.inference_mode():
        for xb, yb in dl:
            preds.append(model(xb.to(device)).argmax(1).cpu().numpy())
            labels.append(yb.numpy())
    cm = confusion_matrix(np.concatenate(preds), np.concatenate(labels), cfg.num_classes)
    return metrics_from_cm(cm)


# ---------------- 微调 ----------------

def finetune(model, cfg, device: str, epochs: int, lr_head: float, lr_backbone: float,
             tag: str = 'ft') -> tuple[dict, list]:
    """剪枝后微调。监控验证集宏观 F1 选最优（与训练期 early_stop_metric 一致）。"""
    cfg.epochs = epochs
    cfg.lr_head = lr_head
    cfg.lr_backbone = lr_backbone

    dl_train, dl_val, _ = build_loaders(cfg)
    cw = make_class_weights(load_split()['train'], cfg.num_classes, cfg.class_weight_power)
    criterion = nn.CrossEntropyLoss(weight=cw.to(device), label_smoothing=cfg.label_smoothing)
    optimizer = Adam(param_groups(model, cfg), weight_decay=cfg.weight_decay)
    scheduler = build_scheduler(optimizer, cfg, len(dl_train))

    best = {'score': -1.0, 'epoch': -1, 'state': None, 'metrics': None}
    history = []
    model.to(device)

    for ep in range(1, epochs + 1):
        t0 = time.time()
        tr_loss, trp, trl = run_epoch(model, dl_train, criterion, optimizer, scheduler,
                                      device, cfg, train=True, epoch_label=f'{tag}{ep}')
        va_loss, vap, val_ = run_epoch(model, dl_val, criterion, None, None,
                                       device, cfg, train=False)
        tm = metrics_from_cm(confusion_matrix(trp, trl, cfg.num_classes))
        vm = metrics_from_cm(confusion_matrix(vap, val_, cfg.num_classes))
        dt = time.time() - t0
        history.append({
            'epoch': ep, 'train_loss': round(tr_loss, 6), 'val_loss': round(va_loss, 6),
            'train_acc': tm['accuracy'], 'val_acc': vm['accuracy'],
            'train_macro_f1': tm['macro_f1'], 'val_macro_f1': vm['macro_f1'],
            'seconds': round(dt, 1),
        })
        mark = ''
        if vm['macro_f1'] > best['score']:
            best = {'score': vm['macro_f1'], 'epoch': ep, 'metrics': vm,
                    'state': {k: v.detach().cpu().clone()
                              for k, v in model.state_dict().items()}}
            mark = '  ↑ 新最优'
        print(f'  ft{ep:02d}/{epochs} | tr_loss {tr_loss:.4f} acc {tm["accuracy"]:.4f} '
              f'F1 {tm["macro_f1"]:.4f} | va_loss {va_loss:.4f} acc {vm["accuracy"]:.4f} '
              f'F1 {vm["macro_f1"]:.4f} | {dt:.0f}s{mark}')

    return best, history


# ---------------- 主流程 ----------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--ratio', type=float, default=0.30, help='目标剪枝比例（PRD 上限 0.30）')
    ap.add_argument('--min-keep-ratio', type=float, default=0.40, help='单层至少保留比例')
    ap.add_argument('--ft-epochs', type=int, default=8, help='剪后微调轮数；0 表示不微调')
    ap.add_argument('--lr-head', type=float, default=3e-4)
    ap.add_argument('--lr-backbone', type=float, default=3e-5)
    ap.add_argument('--tag', default=None, help='产物名后缀，默认由 ratio 生成')
    ap.add_argument('--dry-run', action='store_true', help='只做剪枝与结构核对，不微调不评估')
    ap.add_argument('--cpu-eval', action='store_true', help='额外测 CPU 耗时')
    ap.add_argument('--protect-first-layer', action='store_true',
                    help='保护首层：stage1 与 stem 不剪（对照实验）')
    args = ap.parse_args()

    ensure_dirs()
    pct = int(round(args.ratio * 100))
    suffix = '_protectstem' if args.protect_first_layer else ''
    tag = args.tag or f'p{pct}{suffix}'
    name = f'M1_main_224_pruned{pct}{suffix}_ft'
    device = pick_device()

    print('=' * 78)
    print(' 海瞳鱼鉴 · M3.5 结构化剪枝')
    print('=' * 78)
    print(f'  设备: {device}   目标剪枝比例 {args.ratio:.0%}   微调 {args.ft_epochs} 轮')
    print()

    model, cfg, ckpt = load_baseline()
    base_params = param_count(model)
    base_bytes = serialized_bytes(model)
    print(f'  基线: 参数 {base_params:,} / 体积 {base_bytes/1024**2:.3f} MB')
    print()

    # ---- 1. 选通道 ----
    print('-' * 78)
    print(' 1. 通道重要性评估与选择')
    print('-' * 78)
    keep_map, sel = select_channels(model, args.ratio, args.min_keep_ratio,
                                    args.protect_first_layer)
    print()

    # ---- 2. 重建 ----
    print('-' * 78)
    print(' 2. 结构重建（真正减参，非掩码置零）')
    print('-' * 78)
    pruned = rebuild_with_channels(model, keep_map)
    pr_params = param_count(pruned)
    pr_bytes = serialized_bytes(pruned)
    info_b, info_p = count_conv_linear_channels(model), count_conv_linear_channels(pruned)
    print(f'  参数量  {base_params:,} → {pr_params:,}  '
          f'（减少 {base_params - pr_params:,}，{(1-pr_params/base_params):.2%}）')
    print(f'  体积    {base_bytes/1024**2:.3f} MB → {pr_bytes/1024**2:.3f} MB '
          f'（减少 {(1-pr_bytes/base_bytes):.2%}）')
    print(f'  conv 参数 {info_b["conv_total_params"]:,} → {info_p["conv_total_params"]:,}')
    print(f'  conv 通道  {info_b["conv"][-1]["out"]} 层末 → {info_p["conv"][-1]["out"]}；'
          f'fc 输入 {info_b["linear"][0]["in"]} → {info_p["linear"][0]["in"]}')

    # 结构自检：一次前向必须通过（维度错配会在此立即暴露）
    probe = torch.randn(2, 3, 224, 224).to(device)
    pruned.to(device)
    with torch.inference_mode():
        out = pruned(probe)
    pruned.to('cpu')
    assert out.shape == (2, cfg.num_classes), f'输出形状异常: {tuple(out.shape)}'
    print(f'  ✓ 结构自检通过：前向输出 {tuple(out.shape)}')

    gpu_bench = bench_forward(pruned, DEVICE_GPU) if torch.cuda.is_available() else None
    cpu_bench = bench_forward(pruned, DEVICE_CPU) if args.cpu_eval else None
    if gpu_bench:
        print(f'  剪枝后 GPU 前向 p50 {gpu_bench["p50_ms"]:.3f} ms')
    print()

    if args.dry_run:
        d = model_dir(name)
        torch.save({'state_dict': pruned.state_dict(), 'keep_map': keep_map,
                    'config': cfg.to_dict(), 'selection': sel,
                    'species_index_to_cn': INDEX_TO_CN,
                    'species_index_to_sci': INDEX_TO_SCI},
                   os.path.join(d, 'dryrun.pt'))
        print(f'  --dry-run：产物写入 {os.path.join(d, "dryrun.pt")}，未微调未评估')
        return 0

    # ---- 3. 微调前基线（val 口径） ----
    print('-' * 78)
    print(' 3. 验证集上的剪枝即时损失（未微调）')
    print('-' * 78)
    val_before = eval_on_val(pruned, cfg, device)
    print(f'  剪枝未微调  val acc {val_before["accuracy"]:.6f}  '
          f'macroF1 {val_before["macro_f1"]:.6f}  '
          f'（{sum(val_before["per_class_support"]):,} 张）')
    base_val = eval_on_val(model, cfg, device)
    print(f'  基线对照    val acc {base_val["accuracy"]:.6f}  '
          f'macroF1 {base_val["macro_f1"]:.6f}')
    d_val_f1 = val_before['macro_f1'] - base_val['macro_f1']
    print(f'  即时回退    acc {(val_before["accuracy"]-base_val["accuracy"])*100:+.2f} pp / '
          f'macroF1 {d_val_f1*100:+.2f} pp')
    print()

    # ---- 4. 微调 ----
    best, history = None, []
    if args.ft_epochs > 0:
        print('-' * 78)
        print(f' 4. 剪后微调（{args.ft_epochs} 轮，lr_head={args.lr_head}, '
              f'lr_backbone={args.lr_backbone}）')
        print('-' * 78)
        best, history = finetune(pruned, cfg, device, args.ft_epochs,
                                 args.lr_head, args.lr_backbone, tag=tag)
        print(f'  最优轮次 ep{best["epoch"]}  val macroF1 {best["score"]:.6f}')
        pruned.load_state_dict(best['state'])
        pruned.to('cpu').eval()
    else:
        print('  （--ft-epochs 0：跳过微调）')
    print()

    # ---- 5. 落盘 ----
    d = model_dir(name)
    out_path = os.path.join(d, 'best.pt')
    cfg_out = cfg.to_dict()
    torch.save({
        'state_dict': pruned.state_dict(),
        'config': cfg_out,
        'epoch': best['epoch'] if best else None,
        'metrics': best['metrics'] if best else val_before,
        'species_index_to_cn': INDEX_TO_CN,
        'species_index_to_sci': INDEX_TO_SCI,
        'keep_map': keep_map,
        'optimize': {
            'method': 'structured_channel_pruning_bn_gamma + finetune',
            'target_ratio': args.ratio,
            'actual_sparsity': sel['actual_sparsity'],
            'min_keep_ratio': args.min_keep_ratio,
            'ft_epochs': args.ft_epochs,
            'ft_lr': {'head': args.lr_head, 'backbone': args.lr_backbone},
            'base_params': base_params, 'pruned_params': pr_params,
            'base_mb': round(base_bytes / 1024 ** 2, 3),
            'pruned_mb': round(pr_bytes / 1024 ** 2, 3),
            'rebuild_hint': '用 rebuild_with_channels(load_baseline()[0], keep_map) 重建空壳',
        },
    }, out_path)

    meta = {
        'name': name,
        'method': 'structured_channel_pruning + finetune',
        'model_path': out_path,
        'file_mb_on_disk': round(os.path.getsize(out_path) / 1024 ** 2, 3),
        'serialized_mb': round(pr_bytes / 1024 ** 2, 3),
        'base_serialized_mb': round(base_bytes / 1024 ** 2, 3),
        'param_count': pr_params,
        'base_param_count': base_params,
        'selection': sel,
        'keep_map': keep_map,
        'val_baseline': base_val,
        'val_pruned_no_ft': val_before,
        'val_best_ft': best['metrics'] if best else None,
        'ft_history': history,
        'bench_gpu_ms': gpu_bench,
        'bench_cpu_ms': cpu_bench,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    save_json(meta, os.path.join(d, 'meta.json'))

    print('-' * 78)
    print(' 5. 产物')
    print('-' * 78)
    print(f'  权重: {out_path}  ({meta["file_mb_on_disk"]:.3f} MB)')
    print(f'  元数据: {os.path.join(d, "meta.json")}')
    print()
    print(f'  注：本脚本只报告 val 口径。test 划分留待 compare.py 一次性复测。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
