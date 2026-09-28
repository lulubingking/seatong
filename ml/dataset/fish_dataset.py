# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 数据集 Dataset 与 DataLoader 构建

要点：
  1. 读取 make_split.py 产出的 split.json（不重新划分，保证可复现）
  2. 训练集走增强变换，val/test 走确定性变换 —— 二者均取自 ml/dataset/preprocess.py
  3. 长尾处理：WeightedRandomSampler 按类别反频率采样（对应核心风险 R-D-01）
  4. 类别权重用于损失函数（可选，与采样器二选一或叠加）
"""

import io
import json
import os
import sys
from collections import Counter

import torch
from PIL import Image
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.dirname(_HERE))

from preprocess import build_eval_transform, build_train_transform, load_image_rgb  # noqa: E402
from species_meta import NUM_CLASSES  # noqa: E402
from config import DATA_ROOT, DATASET_DIR, TrainConfig  # noqa: E402

SPLIT_JSON = os.path.join(DATASET_DIR, 'split.json')


class FishDataset(Dataset):
    """海洋鱼类数据集。返回 (tensor, label)。"""

    def __init__(self, records: list[dict], transform, data_root: str = DATA_ROOT):
        self.records = records
        self.transform = transform
        self.data_root = data_root
        self._cache: dict[str, list] = {}

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int):
        rec = self.records[idx]
        path = os.path.join(self.data_root, rec['path'])
        try:
            with Image.open(path) as im:
                im.load()
                img = load_image_rgb(im)
                tensor = self.transform(img)
            return tensor, rec['class_index']
        except Exception:
            # 损坏图片的兜底：返回另一张同类的图，避免整批训练崩溃。
            # 正常数据集不应触发；若频繁触发说明数据有质量问题，须单独排查。
            same = self._cache.get(rec['dir_name'])
            if same is None:
                same = [r for r in self.records if r['dir_name'] == rec['dir_name']]
                self._cache[rec['dir_name']] = same
            alt = same[(idx + 1) % len(same)] if len(same) > 1 else rec
            p2 = os.path.join(self.data_root, alt['path'])
            with Image.open(p2) as im2:
                return self.transform(load_image_rgb(im2)), alt['class_index']

    def labels(self) -> list[int]:
        return [r['class_index'] for r in self.records]


def load_split(split_json: str = SPLIT_JSON) -> dict:
    with io.open(split_json, encoding='utf-8') as f:
        return json.load(f)


def make_class_weights(records: list[dict], num_classes: int = NUM_CLASSES,
                       power: float = 0.5) -> torch.Tensor:
    """类别权重 = (总数 / 该类计数) ^ power，再归一到均值为 1。

    power=0   → 全 1（等价不加权）
    power=1   → 完全反频率（极端，尾部类梯度会爆）
    power=0.5 → 温和折中（默认）
    """
    counts = Counter(r['class_index'] for r in records)
    total = sum(counts.values())
    w = torch.ones(num_classes, dtype=torch.float32)
    for c in range(num_classes):
        n = counts.get(c, 0)
        w[c] = (total / n) ** power if n > 0 else 0.0
    w = w / w[w > 0].mean()      # 归一化到均值 1，保持整体学习率尺度
    return w


def make_sampler(records: list[dict], num_classes: int = NUM_CLASSES,
                 power: float = 0.5) -> WeightedRandomSampler:
    """按类别反频率采样，使每个 epoch 中各"类别"被抽到的总量趋于均衡。

    注意：是类别均衡，不是样本均衡 —— 头部类的单张样本被重复抽取的概率更低。
    """
    weights = make_class_weights(records, num_classes, power)
    sample_w = torch.tensor([float(weights[r['class_index']]) for r in records],
                            dtype=torch.double)
    return WeightedRandomSampler(weights=sample_w, num_samples=len(records), replacement=True)


def build_loaders(cfg: TrainConfig, split_json: str = SPLIT_JSON,
                  verbose: bool = True):
    """构建 train / val / test 三个 DataLoader。"""
    split = load_split(split_json)

    ds_train = FishDataset(split['train'], build_train_transform())
    ds_val = FishDataset(split['val'], build_eval_transform())
    ds_test = FishDataset(split['test'], build_eval_transform())

    sampler = None
    shuffle = True
    if cfg.weighted_sampler:
        sampler = make_sampler(split['train'], cfg.num_classes, cfg.class_weight_power)
        shuffle = False        # 用 sampler 时不能再 shuffle

    common = dict(num_workers=cfg.num_workers, pin_memory=True,
                  persistent_workers=cfg.num_workers > 0)
    dl_train = DataLoader(ds_train, batch_size=cfg.batch_size, sampler=sampler,
                          shuffle=shuffle, drop_last=True, **common)
    dl_val = DataLoader(ds_val, batch_size=cfg.batch_size, shuffle=False, **common)
    dl_test = DataLoader(ds_test, batch_size=cfg.batch_size, shuffle=False, **common)

    if verbose:
        print(f'  训练集 {len(ds_train):,} 张 / {len(dl_train)} 批'
              f'{"（WeightedRandomSampler 已启用）" if sampler else ""}')
        print(f'  验证集 {len(ds_val):,} 张 / {len(dl_val)} 批')
        print(f'  测试集 {len(ds_test):,} 张 / {len(dl_test)} 批')

        w = make_class_weights(split['train'], cfg.num_classes, cfg.class_weight_power)
        head = w.topk(4)
        tail = w.topk(4, largest=False)
        print(f'  类别权重 max/mean = {w.max():.2f} / min(非零) = '
              f'{w[w > 0].min():.2f} （power={cfg.class_weight_power}）')
        print(f'    最高权 4 类 idx: {head.indices.tolist()} 值 {[round(x, 2) for x in head.values.tolist()]}')
        print(f'    最低权 4 类 idx: {tail.indices.tolist()} 值 {[round(x, 2) for x in tail.values.tolist()]}')

    return dl_train, dl_val, dl_test


if __name__ == '__main__':
    cfg = TrainConfig()
    print('=' * 76)
    print('数据集与 DataLoader 冒烟测试')
    print('=' * 76)
    print()
    if not os.path.exists(SPLIT_JSON):
        print(f'  ! 未找到 {SPLIT_JSON}，请先运行 make_split.py')
        sys.exit(1)

    dl_train, dl_val, dl_test = build_loaders(cfg)
    print()
    print('  取一个批次验证形状...')
    xb, yb = next(iter(dl_train))
    print(f'    x: {tuple(xb.shape)} {xb.dtype}  y: {tuple(yb.shape)} {yb.dtype}')
    print(f'    x 值域: min={xb.min():.3f} max={xb.max():.3f}')
    print(f'    y 取值: {sorted(set(yb.tolist()))}')
    print()
    print('  ✓ DataLoader 就绪')
