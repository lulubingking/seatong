# -*- coding: utf-8 -*-
"""网图混合微调 —— M1_main_224 + ood_web_tune 网图池

【纪律】
  · 起点 = 交付模型 M1_main_224/best.pt（不是 ImageNet 从头训）；
  · 微调数据 = 原训练集（split.json train，同分布锚）+ 网图池（新域）；
  · 验证 = 原验证集（防遗忘闸）+ 冻结 93 张 OOD 基准（ml/ood_web，提升判据）；
    两者与网图池零重叠。
【选点规则】在各 epoch 权重中，选「OOD Top-1 最高 且 原验证 acc/F1 回退 ≤1pp」的epoch；
  若无 epoch 满足回退门槛，输出全部轨迹并判定微调失败（不交付）。
"""

import io
import json
import os
import sys

import numpy as np
import torch
from torch.utils.data import DataLoader, ConcatDataset

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for p in (_ROOT, os.path.join(_ROOT, 'ml'), os.path.join(_ROOT, 'ml', 'dataset'),
          os.path.join(_ROOT, 'ml', 'training')):
    if p not in sys.path:
        sys.path.insert(0, p)

from fish_dataset import FishDataset, build_train_transform, build_eval_transform, \
    make_sampler, load_split                               # noqa: E402
from preprocess import preprocess_for_inference            # noqa: E402
from species_meta import SPECIES, INDEX_TO_CN, INDEX_TO_SCI  # noqa: E402
from config import pick_device                             # noqa: E402
from train import build_model, param_groups, run_epoch, confusion_matrix, \
    metrics_from_cm                                        # noqa: E402
from optimize.common import load_baseline                  # noqa: E402

TUNE_DIR = os.path.join(_ROOT, 'ml', 'ood_web_tune')
OOD_BENCH_DIR = os.path.join(_ROOT, 'ml', 'ood_web')
OUT_DIR = os.path.join(_ROOT, 'ml', 'models', 'M1_ood_tuned')
# 同分布回退门槛（PRD §7.5 精度控制线）
GATE_PP = 0.01
# M1 ep11 验证集冻结值（同分布锚点）
BASE_VAL = {'acc': 0.997074, 'macro_f1': 0.975185}
EPOCHS = 4
LR_HEAD, LR_BACKBONE = 1e-4, 1e-5


def web_records() -> list[dict]:
    recs = []
    for sp in SPECIES:
        d = os.path.join(TUNE_DIR, f'fish_{sp.class_index + 1}')
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith(('.jpg', '.jpeg', '.png')):
                recs.append({'path': os.path.join(d, fn),
                             'class_index': sp.class_index,
                             'dir_name': f'fish_{sp.class_index + 1}'})
    return recs


@torch.inference_mode()
def ood_eval(model, device) -> dict:
    """冻结 93 张 OOD 基准（prod 预处理口径，与基线 32.26% 可比）。"""
    model.eval()
    n = t1 = t5 = 0
    confs = []
    for sp in SPECIES:
        d = os.path.join(OOD_BENCH_DIR, f'fish_{sp.class_index + 1}')
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue
            try:
                tensor = preprocess_for_inference(os.path.join(d, fn))
            except Exception:                        # noqa: BLE001
                continue
            logits = model(tensor.to(device))
            probs = torch.softmax(logits.float(), dim=1)[0]
            vals, idxs = torch.topk(probs, 5)
            n += 1
            t1 += int(int(idxs[0]) == sp.class_index)
            t5 += int(sp.class_index in idxs.tolist())
            confs.append(float(vals[0]))
    return {'n': n, 'top1': round(t1 / n, 4) if n else None,
            'top5': round(t5 / n, 4) if n else None,
            'mean_conf': round(float(np.mean(confs)), 4) if confs else None}


def main() -> int:
    device = pick_device()
    torch.manual_seed(20260921)
    np.random.seed(20260921)
    if device.type == 'cuda':
        torch.backends.cudnn.benchmark = True

    model, cfg, _ckpt = load_baseline()
    model.to(device)
    groups = param_groups(model, cfg)
    for g in groups:
        g['lr'] = LR_HEAD if g.get('name') == 'head' else LR_BACKBONE
        g['initial_lr'] = g['lr']
    optimizer = torch.optim.Adam(groups, weight_decay=cfg.weight_decay)

    split = load_split()
    tf_train, tf_eval = build_train_transform(), build_eval_transform()
    ds_indoor = FishDataset(split['train'], tf_train)
    web = web_records()
    ds_web = FishDataset(web, tf_train, data_root='') if web else None
    print(f'同分布训练 {len(ds_indoor)} 张 + 网图 {len(web)} 张')

    ds_mix = ds_indoor if ds_web is None else ConcatDataset([ds_indoor, ds_web])
    recs_mix = split['train'] + web
    sampler = make_sampler(recs_mix, cfg.num_classes, cfg.class_weight_power)
    dl_train = DataLoader(ds_mix, batch_size=cfg.batch_size, sampler=sampler,
                          drop_last=True, num_workers=cfg.num_workers,
                          pin_memory=True, persistent_workers=cfg.num_workers > 0)
    dl_val = DataLoader(FishDataset(split['val'], tf_eval),
                        batch_size=cfg.batch_size, shuffle=False,
                        num_workers=cfg.num_workers, pin_memory=True)
    criterion = torch.nn.CrossEntropyLoss(label_smoothing=cfg.label_smoothing)

    import time
    os.makedirs(OUT_DIR, exist_ok=True)
    traj = []
    best_pick = None
    states = {}
    for ep in range(1, EPOCHS + 1):
        t0 = time.time()
        tr_loss, _p, _l = run_epoch(model, dl_train, criterion, optimizer, None,
                                    device, cfg, train=True, epoch_label=f'ep{ep}')
        _vl, vp, vl = run_epoch(model, dl_val, criterion, None, None,
                                device, cfg, train=False)
        vm = metrics_from_cm(confusion_matrix(vp, vl, cfg.num_classes))
        ood = ood_eval(model, device)
        gate = (vm['accuracy'] >= BASE_VAL['acc'] - GATE_PP and
                vm['macro_f1'] >= BASE_VAL['macro_f1'] - GATE_PP)
        traj.append({'epoch': ep, 'train_loss': round(tr_loss, 4),
                     # 契约键（与 M1_main_224 checkpoint schema 对齐，probe/前端按此读取）
                     'accuracy': vm['accuracy'], 'macro_f1': vm['macro_f1'],
                     'val_acc': vm['accuracy'], 'val_macro_f1': vm['macro_f1'],
                     'ood_top1': ood['top1'], 'ood_top5': ood['top5'],
                     'ood_mean_conf': ood['mean_conf'], 'gate_pass': gate,
                     'seconds': round(time.time() - t0)})
        print(f"ep{ep}: val acc {vm['accuracy']:.4f} F1 {vm['macro_f1']:.4f} | "
              f"OOD top1 {ood['top1']} top5 {ood['top5']} | gate={gate}", flush=True)
        states[ep] = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if gate and (best_pick is None or ood['top1'] > best_pick[1]['ood_top1']):
            best_pick = (ep, traj[-1])

    result = {
        'baseline': {'val': BASE_VAL, 'ood_top1': 0.3226, 'ood_top5': 0.6344},
        'config': {'epochs': EPOCHS, 'lr_head': LR_HEAD,
                   'lr_backbone': LR_BACKBONE, 'web_images': len(web),
                   'gate_pp': GATE_PP},
        'trajectory': traj,
        'picked_epoch': best_pick[0] if best_pick else None,
    }
    if best_pick:
        ep = best_pick[0]
        model.load_state_dict(states[ep])
        torch.save({'state_dict': states[ep], 'config': cfg.to_dict(),
                    'epoch': ep, 'metrics': best_pick[1],
                    'species_index_to_cn': INDEX_TO_CN,
                    'species_index_to_sci': INDEX_TO_SCI,
                    'finetune': result['config']},
                   os.path.join(OUT_DIR, 'best.pt'))
        print(f"选定 ep{ep}（OOD {best_pick[1]['ood_top1']}）→ {OUT_DIR}/best.pt")
    else:
        print('无 epoch 通过同分布回退门槛 → 不交付（权重未保存为 best.pt）')
    with io.open(os.path.join(OUT_DIR, 'finetune_report.json'), 'w',
                 encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"报告 → {OUT_DIR}/finetune_report.json")
    return 0


if __name__ == '__main__':
    sys.exit(main())
