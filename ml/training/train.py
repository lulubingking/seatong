# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · ResNet18 迁移学习训练脚本

对应任务书"算法四阶段"的第二阶段（训练）：
    迁移学习 + 交叉熵 + Adam + 余弦退火 + 早停

硬指标（PRD §4）：
    准确率   ≥ 85%
    宏观 F1  ≥ 0.82      ← 真正的难点，因长尾失衡（头部 4 类占 82.1%）

长尾应对（核心风险 R-D-01）：
    · WeightedRandomSampler 反频率采样
    · 类别加权损失（power=0.5 温和折中）
    · label_smoothing 缓解头部过自信
    · 差分学习率：新分类头 1e-3 / 预训练主干 1e-4

用法：
    python train.py                          # 默认配置
    python train.py --run-name baseline_224  # 指定运行名
    python train.py --epochs 5 --no-amp      # 快速冒烟
"""

import argparse
import io
import json
import os
import sys
import time
from dataclasses import asdict

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import Adam
from torch.optim.lr_scheduler import CosineAnnealingLR, LambdaLR, SequentialLR

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'dataset'))
sys.path.insert(0, os.path.dirname(_HERE))

from config import TrainConfig, MODELS_DIR, REPORTS_DIR, pick_device, device_summary, ensure_dirs  # noqa: E402
from species_meta import NUM_CLASSES, INDEX_TO_CN, INDEX_TO_SCI  # noqa: E402
from fish_dataset import build_loaders, load_split, make_class_weights  # noqa: E402


# ---------------- 指标 ----------------

def confusion_matrix(preds: np.ndarray, labels: np.ndarray, n: int) -> np.ndarray:
    cm = np.zeros((n, n), dtype=np.int64)
    for t, p in zip(labels, preds):
        cm[t, p] += 1
    return cm


def metrics_from_cm(cm: np.ndarray) -> dict:
    """从混淆矩阵算全套指标。宏观值对缺项类别按 0 处理并单独报出缺失类别。"""
    n = cm.shape[0]
    tp = np.diag(cm).astype(np.float64)
    fp = cm.sum(axis=0).astype(np.float64) - tp
    fn = cm.sum(axis=1).astype(np.float64) - tp
    support = cm.sum(axis=1).astype(np.float64)

    prec = np.divide(tp, tp + fp, out=np.zeros(n), where=(tp + fp) > 0)
    rec = np.divide(tp, tp + fn, out=np.zeros(n), where=(tp + fn) > 0)
    f1 = np.divide(2 * prec * rec, prec + rec, out=np.zeros(n), where=(prec + rec) > 0)

    present = support > 0
    total = cm.sum()
    acc = float(tp.sum() / total) if total > 0 else 0.0

    return {
        'accuracy': round(acc, 6),
        'macro_precision': round(float(prec[present].mean()) if present.any() else 0.0, 6),
        'macro_recall': round(float(rec[present].mean()) if present.any() else 0.0, 6),
        'macro_f1': round(float(f1[present].mean()) if present.any() else 0.0, 6),
        'weighted_f1': round(float((f1 * support).sum() / total) if total > 0 else 0.0, 6),
        'per_class_f1': [round(float(x), 6) for x in f1],
        'per_class_precision': [round(float(x), 6) for x in prec],
        'per_class_recall': [round(float(x), 6) for x in rec],
        'per_class_support': [int(x) for x in support],
        'macro_f1_over_present_classes': round(float(f1[present].mean()) if present.any() else 0.0, 6),
    }


# ---------------- 模型 ----------------

def build_model(cfg: TrainConfig) -> nn.Module:
    """ResNet18 + 迁移学习。分类头替换为 Dropout + Linear(512→23)。"""
    from torchvision import models
    weights = models.ResNet18_Weights.IMAGENET1K_V1 if cfg.pretrained else None
    m = models.resnet18(weights=weights)
    in_features = m.fc.in_features
    m.fc = nn.Sequential(
        nn.Dropout(p=cfg.dropout),
        nn.Linear(in_features, cfg.num_classes),
    )
    return m


def param_groups(model: nn.Module, cfg: TrainConfig) -> list[dict]:
    """差分学习率：分类头用大 lr，预训练主干用小 lr。"""
    head_ids = {id(p) for p in model.fc.parameters()}
    head = [p for p in model.parameters() if id(p) in head_ids]
    backbone = [p for p in model.parameters() if id(p) not in head_ids]
    return [
        {'params': head, 'lr': cfg.lr_head, 'name': 'head'},
        {'params': backbone, 'lr': cfg.lr_backbone, 'name': 'backbone'},
    ]


def build_scheduler(optimizer, cfg: TrainConfig, steps_per_epoch: int):
    """warmup（线性升温）→ 余弦退火到 eta_min。"""
    total_steps = cfg.epochs * steps_per_epoch
    warm = cfg.warmup_epochs * steps_per_epoch
    if warm <= 0:
        return CosineAnnealingLR(optimizer, T_max=total_steps, eta_min=cfg.eta_min)

    def warm_fn(step):
        return (step + 1) / max(1, warm)

    warm_sched = LambdaLR(optimizer, warm_fn)
    cos_sched = CosineAnnealingLR(optimizer, T_max=max(1, total_steps - warm),
                                 eta_min=cfg.eta_min)
    return SequentialLR(optimizer, [warm_sched, cos_sched], milestones=[warm])


# ---------------- 训练 / 评估 ----------------

def run_epoch(model, loader, criterion, optimizer, scheduler, device, cfg,
              train: bool, scaler=None, epoch_label: str = '') -> tuple[float, np.ndarray, np.ndarray]:
    model.train(train)
    total_loss, n_seen = 0.0, 0
    all_preds, all_labels = [], []
    amp_dtype = torch.bfloat16 if cfg.amp_dtype == 'bf16' else torch.float16

    ctx = torch.enable_grad() if train else torch.no_grad()
    with ctx:
        for bi, (xb, yb) in enumerate(loader):
            xb = xb.to(device, non_blocking=True)
            yb = yb.to(device, non_blocking=True)

            if train and cfg.amp:
                with torch.autocast(device_type=device.type, dtype=amp_dtype):
                    logits = model(xb)
                    loss = criterion(logits, yb)
            else:
                logits = model(xb)
                loss = criterion(logits, yb)

            if train:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
                optimizer.step()
                if scheduler is not None:
                    scheduler.step()

            total_loss += loss.item() * yb.size(0)
            n_seen += yb.size(0)
            all_preds.append(logits.detach().float().argmax(1).cpu().numpy())
            all_labels.append(yb.detach().cpu().numpy())

            if train and (bi + 1) % 50 == 0:
                print(f'      [{epoch_label}] 批 {bi + 1}/{len(loader)}  '
                      f'loss={total_loss / n_seen:.4f}', end='\r', flush=True)

    preds = np.concatenate(all_preds) if all_preds else np.zeros(0, dtype=int)
    labels = np.concatenate(all_labels) if all_labels else np.zeros(0, dtype=int)
    return total_loss / max(1, n_seen), preds, labels


# ---------------- 主流程 ----------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-name', default=None)
    ap.add_argument('--epochs', type=int, default=None)
    ap.add_argument('--batch-size', type=int, default=None)
    ap.add_argument('--img-size', type=int, default=None)
    ap.add_argument('--lr-head', type=float, default=None)
    ap.add_argument('--lr-backbone', type=float, default=None)
    ap.add_argument('--no-amp', action='store_true')
    ap.add_argument('--no-sampler', action='store_true')
    ap.add_argument('--no-class-weight', action='store_true',
                    help='损失函数不使用类别加权（检验采样器是否已足够）')
    ap.add_argument('--num-workers', type=int, default=None)
    ap.add_argument('--smoke', action='store_true', help='极小规模冒烟：2 类子集 + 1 epoch')
    args = ap.parse_args()

    cfg = TrainConfig()
    if args.run_name: cfg.run_name = args.run_name
    if args.epochs: cfg.epochs = args.epochs
    if args.batch_size: cfg.batch_size = args.batch_size
    if args.img_size: cfg.img_size = args.img_size
    if args.lr_head: cfg.lr_head = args.lr_head
    if args.lr_backbone: cfg.lr_backbone = args.lr_backbone
    if args.no_amp: cfg.amp = False
    if args.no_sampler: cfg.weighted_sampler = False
    if args.num_workers is not None: cfg.num_workers = args.num_workers
    use_class_weight = not args.no_class_weight

    ensure_dirs()
    device = pick_device()

    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    if device.type == 'cuda':
        torch.cuda.manual_seed_all(cfg.seed)
        torch.backends.cudnn.benchmark = True

    print('=' * 78)
    print(f'海瞳鱼鉴 · ResNet18 迁移学习训练  [{cfg.run_name}]')
    print('=' * 78)
    print(f'  {device_summary()}')
    print()

    # ---- 数据 ----
    print('  构建数据加载器...')
    if cfg.img_size != 224:
        # 若改输入尺寸，动态覆写预处理口径（保持单一来源原则）
        import preprocess as P
        P.IMG_SIZE = cfg.img_size
        P.RESIZE_SHORT = int(cfg.img_size * 256 / 224)
        P._EVAL_TF = None
        print(f'    ! 输入尺寸覆写为 {cfg.img_size}（短边 {P.RESIZE_SHORT}）')
    dl_train, dl_val, dl_test = build_loaders(cfg)
    print()

    # ---- 模型 / 损失 / 优化器 ----
    model = build_model(cfg).to(device)
    n_param = sum(p.numel() for p in model.parameters())
    n_train_p = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f'  模型 {cfg.arch}: 参数 {n_param:,}（可训练 {n_train_p:,}）')

    split = load_split()
    class_w = make_class_weights(split['train'], cfg.num_classes, cfg.class_weight_power)
    criterion = nn.CrossEntropyLoss(
        weight=class_w.to(device) if use_class_weight else None,
        label_smoothing=cfg.label_smoothing)
    print(f'  损失: CrossEntropyLoss('
          f'weight={"类别加权(power=" + str(cfg.class_weight_power) + ")" if use_class_weight else "不加权"}, '
          f'label_smoothing={cfg.label_smoothing})')

    optimizer = Adam(param_groups(model, cfg), weight_decay=cfg.weight_decay)
    scheduler = build_scheduler(optimizer, cfg, len(dl_train))
    print(f'  优化器: Adam(lr_head={cfg.lr_head}, lr_backbone={cfg.lr_backbone}, '
          f'wd={cfg.weight_decay})')
    print(f'  调度: warmup {cfg.warmup_epochs} ep → 余弦退火至 {cfg.eta_min}')
    print(f'  早停: 监控 {cfg.early_stop_metric}，patience={cfg.early_stop_patience}')
    print(f'  混合精度: {"开 (" + cfg.amp_dtype + ")" if cfg.amp else "关"}')
    print()

    # ---- 落盘配置 ----
    run_dir = os.path.join(MODELS_DIR, cfg.run_name)
    os.makedirs(run_dir, exist_ok=True)
    cfg_dict = cfg.to_dict()
    cfg_dict['use_class_weight'] = use_class_weight
    with io.open(os.path.join(run_dir, 'run_config.json'), 'w', encoding='utf-8') as f:
        json.dump({'config': cfg_dict, 'device': str(device),
                   'torch': torch.__version__, 'cuda': torch.version.cuda,
                   'gpu': torch.cuda.get_device_name(0) if device.type == 'cuda' else None},
                  f, ensure_ascii=False, indent=1)

    # ---- 训练循环 ----
    history = []
    best = {'score': -1.0, 'epoch': -1, 'state': None, 'metrics': None}
    bad_epochs = 0
    t_start = time.time()

    print('  开始训练')
    print('  ' + '-' * 74)
    for ep in range(1, cfg.epochs + 1):
        t0 = time.time()
        tr_loss, tr_pred, tr_lab = run_epoch(model, dl_train, criterion, optimizer,
                                             scheduler, device, cfg, train=True,
                                             epoch_label=f'ep{ep}')
        va_loss, va_pred, va_lab = run_epoch(model, dl_val, criterion, None,
                                             None, device, cfg, train=False)

        tr_m = metrics_from_cm(confusion_matrix(tr_pred, tr_lab, cfg.num_classes))
        va_m = metrics_from_cm(confusion_matrix(va_pred, va_lab, cfg.num_classes))
        lr_now = optimizer.param_groups[0]['lr']
        dt = time.time() - t0

        rec = {
            'epoch': ep,
            'train_loss': round(tr_loss, 6), 'val_loss': round(va_loss, 6),
            'train_acc': tr_m['accuracy'], 'val_acc': va_m['accuracy'],
            'train_macro_f1': tr_m['macro_f1'], 'val_macro_f1': va_m['macro_f1'],
            'lr_head': lr_now, 'seconds': round(dt, 1),
        }
        history.append(rec)

        # 达标标记
        hit = ''
        if va_m['accuracy'] >= cfg.target_accuracy and va_m['macro_f1'] >= cfg.target_macro_f1:
            hit = '  ★双达标'
        elif va_m['accuracy'] >= cfg.target_accuracy:
            hit = '  △仅准确率达标'
        elif va_m['macro_f1'] >= cfg.target_macro_f1:
            hit = '  △仅宏观F1达标'

        print(f'  ep{ep:02d}/{cfg.epochs} | tr_loss {tr_loss:.4f} acc {tr_m["accuracy"]:.4f} '
              f'F1 {tr_m["macro_f1"]:.4f} | va_loss {va_loss:.4f} acc {va_m["accuracy"]:.4f} '
              f'F1 {va_m["macro_f1"]:.4f} | {dt:.0f}s{hit}')

        # 早停判定（以宏观 F1 为准）
        score = va_m[cfg.early_stop_metric]
        if score > best['score']:
            best = {
                'score': score, 'epoch': ep, 'metrics': va_m,
                'state': {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
            }
            torch.save({'state_dict': best['state'], 'config': cfg.to_dict(),
                        'epoch': ep, 'metrics': va_m,
                        'species_index_to_cn': INDEX_TO_CN,
                        'species_index_to_sci': INDEX_TO_SCI},
                       os.path.join(run_dir, 'best.pt'))
            bad_epochs = 0
            print(f'        ↑ 新最优（{cfg.early_stop_metric}={score:.4f}），已保存 best.pt')
        else:
            bad_epochs += 1
            if bad_epochs >= cfg.early_stop_patience:
                print(f'        → 早停触发：连续 {bad_epochs} 轮 {cfg.early_stop_metric} 未提升')
                break

    total_min = (time.time() - t_start) / 60

    # ---- 用最优权重评测试集 ----
    print()
    print('  ' + '-' * 74)
    print(f'  训练结束（{total_min:.1f} 分钟）。加载最优权重评测试集...')
    if best['state'] is not None:
        model.load_state_dict(best['state'])
    te_loss, te_pred, te_lab = run_epoch(model, dl_test, criterion, None, None,
                                         device, cfg, train=False)
    te_m = metrics_from_cm(confusion_matrix(te_pred, te_lab, cfg.num_classes))
    cm = confusion_matrix(te_pred, te_lab, cfg.num_classes)

    # ---- 报告 ----
    print()
    print('=' * 78)
    print('  最终结果（测试集）')
    print('=' * 78)
    print(f'  最优轮次        : ep{best["epoch"]}')
    print(f'  准确率          : {te_m["accuracy"]:.4f}   (目标 ≥{cfg.target_accuracy})   '
          f'{"✓ 达标" if te_m["accuracy"] >= cfg.target_accuracy else "✗ 未达标"}')
    print(f'  宏观 F1         : {te_m["macro_f1"]:.4f}   (目标 ≥{cfg.target_macro_f1})   '
          f'{"✓ 达标" if te_m["macro_f1"] >= cfg.target_macro_f1 else "✗ 未达标"}')
    print(f'  加权 F1         : {te_m["weighted_f1"]:.4f}')
    print(f'  宏观精确率/召回 : {te_m["macro_precision"]:.4f} / {te_m["macro_recall"]:.4f}')
    print()
    print('  各类别 F1（按 class_index 升序）:')
    order = sorted(range(cfg.num_classes), key=lambda i: te_m['per_class_f1'][i])
    for i in order:
        bar = '█' * max(1, int(te_m['per_class_f1'][i] * 30))
        print(f'    idx {i:2d} {INDEX_TO_CN[i]:<10s} n={te_m["per_class_support"][i]:5d} '
              f'F1={te_m["per_class_f1"][i]:.3f} {bar}')

    report = {
        'run_name': cfg.run_name,
        'config': cfg_dict,
        'device': str(device),
        'gpu': torch.cuda.get_device_name(0) if device.type == 'cuda' else None,
        'best_epoch': best['epoch'],
        'best_val_metrics': best['metrics'],
        'test_metrics': te_m,
        'test_confusion_matrix': cm.tolist(),
        'history': history,
        'total_minutes': round(total_min, 1),
        'targets': {'accuracy': cfg.target_accuracy, 'macro_f1': cfg.target_macro_f1},
        'targets_met': {
            'accuracy': te_m['accuracy'] >= cfg.target_accuracy,
            'macro_f1': te_m['macro_f1'] >= cfg.target_macro_f1,
        },
    }
    rp = os.path.join(run_dir, 'report.json')
    with io.open(rp, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    np.save(os.path.join(run_dir, 'confusion_matrix.npy'), cm)

    print()
    print(f'  权重: {os.path.join(run_dir, "best.pt")}')
    print(f'  报告: {rp}')
    print(f'  混淆矩阵: {os.path.join(run_dir, "confusion_matrix.npy")}')
    print()
    ok = report['targets_met']['accuracy'] and report['targets_met']['macro_f1']
    print('  结论：' + ('两项硬指标均达标 ✓' if ok else '存在未达标项 ✗ —— 见上方逐项标记'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
