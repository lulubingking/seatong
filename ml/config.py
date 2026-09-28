# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 训练与推理共享配置

所有路径与超参数集中在此，禁止在脚本里散落硬编码。
环境变量前缀 `SEATONG_`（与 PRD §8.5 联调约定一致）。
"""

import os
from dataclasses import dataclass, field, asdict
from typing import Final

# ---------------- 根路径 ----------------
#
# 【可移植性说明】此前 ROOT 硬编码为开发机的绝对路径（E:\...），
# 导致代码一旦被克隆到其他盘符或目录就必然崩溃。现改为：
#   1) 优先读环境变量 SEATONG_ROOT（部署时可用它把数据/模型放到仓库外）；
#   2) 否则以本文件位置向上两级推导 —— 本文件位于 <ROOT>/ml/config.py，
#      故 dirname(dirname(__file__)) 即仓库根，与磁盘位置无关。
# 这样「克隆到任意路径即可运行」成立。

_ML_DIR_SELF: Final[str] = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT: Final[str] = os.path.dirname(_ML_DIR_SELF)

ROOT: Final[str] = os.environ.get('SEATONG_ROOT') or _REPO_ROOT
DATA_ROOT: Final[str] = os.environ.get('SEATONG_DATA_ROOT') or os.path.join(ROOT, 'fish_image23', 'fish_image')
ML_DIR: Final[str] = os.path.join(ROOT, 'ml')
MODELS_DIR: Final[str] = os.path.join(ML_DIR, 'models')
REPORTS_DIR: Final[str] = os.path.join(ML_DIR, 'reports')
DATASET_DIR: Final[str] = os.path.join(ML_DIR, 'dataset')

BACKEND_DIR: Final[str] = os.path.join(ROOT, 'backend')
STORAGE_DIR: Final[str] = os.path.join(BACKEND_DIR, 'storage', 'images')
DB_PATH: Final[str] = os.path.join(BACKEND_DIR, 'data', 'seatong.db')

# ---------------- 训练超参数 ----------------

@dataclass
class TrainConfig:
    """一次训练运行的完整配置。落盘为 run_config.json，保证可复现。"""

    # 数据
    num_classes: int = 23
    img_size: int = 224
    num_workers: int = 4
    seed: int = 20260921

    # 模型
    arch: str = 'resnet18'
    pretrained: bool = True          # 迁移学习：加载 ImageNet 权重
    dropout: float = 0.3             # 分类头前的 dropout（长尾易过拟合）

    # 优化
    epochs: int = 30
    batch_size: int = 64
    lr_head: float = 1e-3            # 新分类头：大学习率
    lr_backbone: float = 1e-4        # 预训练主干：小学习率（差分学习率）
    weight_decay: float = 1e-4
    label_smoothing: float = 0.1     # 缓解头部类过自信

    # 调度：余弦退火 + 早停
    scheduler: str = 'cosine'
    warmup_epochs: int = 2
    eta_min: float = 1e-6
    early_stop_patience: int = 7
    early_stop_metric: str = 'macro_f1'   # 以宏观 F1 为准（PRD 硬指标）

    # 长尾处理（核心风险 R-D-01）
    weighted_sampler: bool = True    # WeightedRandomSampler 反频率采样
    class_weight_power: float = 0.5  # 类别权重 = (1/freq)^power，0.5 为温和折中
    head_downsample: bool = False    # 头部下采样（默认关，先用采样器）
    head_downsample_cap: int = 3000  # 若开启，头部类最多取这么多张

    # 混合精度（RTX 4060 Ada 支持 bf16，速度与显存双收益）
    amp: bool = True
    amp_dtype: str = 'bf16'

    # 目标（PRD §4 硬指标）
    target_accuracy: float = 0.85
    target_macro_f1: float = 0.82

    # 输出
    run_name: str = 'resnet18_baseline'
    save_topk: int = 3

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------- 设备 ----------------

def pick_device():
    """返回可用设备。GPU 优先，CPU 可降级（PRD 部署口径）。"""
    import torch
    if torch.cuda.is_available():
        return torch.device('cuda')
    return torch.device('cpu')


def device_summary() -> str:
    import torch
    if not torch.cuda.is_available():
        return '设备: CPU（未检测到可用 CUDA）'
    d = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(d)
    return (
        f'设备: {props.name} | 显存 {props.total_memory / 1024**3:.1f} GB | '
        f'算力 sm_{props.major}{props.minor} | CUDA {torch.version.cuda} | torch {torch.__version__}'
    )


def ensure_dirs() -> None:
    for d in (MODELS_DIR, REPORTS_DIR, DATASET_DIR, STORAGE_DIR,
              os.path.dirname(DB_PATH), os.path.join(BACKEND_DIR, 'logs')):
        os.makedirs(d, exist_ok=True)


if __name__ == '__main__':
    ensure_dirs()
    print(device_summary())
    print()
    cfg = TrainConfig()
    print('训练配置:')
    for k, v in cfg.to_dict().items():
        print(f'  {k:24s} {v}')
