# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 预处理一致性模块（训练 / 推理共用）

PRD §10.4.2 硬性要求：
    训练与推理两条流水线【必须产出逐元素相同的张量，容差 0】。

实现方式：把预处理定义收敛到本模块【唯一】的 build_eval_transform() /
build_train_transform()，训练侧与推理侧一律从这里取，禁止各自 new 一个 transform。
配套单测 `test_preprocess_parity.py` 用同一张图分别走两条路径，断言 bitwise 相等。

设计口径（对应 PRD 与 D9）：
  - 输入统一 Resize 短边到 256 → CenterCrop 224（推理）/ RandomResizedCrop 224（训练）
  - 归一化用 ImageNet 统计量（迁移学习必须与预训练一致）
  - 推理路径【禁止】任何随机性：无 ColorJitter、无 RandomErasing、无随机翻转
  - 张量布局 NCHW / float32 / RGB（不是 BGR —— cv2 读入需转色）
"""

import io
from typing import Final

from PIL import Image
import torch
from torchvision import transforms
from torchvision.transforms import InterpolationMode

# ---------------- 固定口径常量（不得在别处重复定义） ----------------

IMG_SIZE: Final[int] = 224          # 模型输入边长
RESIZE_SHORT: Final[int] = 256      # 先缩放到短边 256，再中心裁剪 224

# ImageNet 统计量：ResNet18 预训练权重配套，迁移学习必须沿用
IMAGENET_MEAN: Final[tuple[float, float, float]] = (0.485, 0.456, 0.406)
IMAGENET_STD: Final[tuple[float, float, float]] = (0.229, 0.224, 0.225)

# 训练增强强度（可调，但必须记录到训练配置里）
TRAIN_CROP_SCALE: Final[tuple[float, float]] = (0.7, 1.0)
TRAIN_ROTATION_DEG: Final[int] = 12
TRAIN_COLOR_JITTER: Final[tuple[float, float, float, float]] = (0.2, 0.2, 0.2, 0.03)


# ---------------- 变换构建（唯一入口） ----------------

def build_eval_transform() -> transforms.Compose:
    """推理 / 验证 / 测试 使用的确定性预处理。

    【必须】与训练侧的验证分支完全相同，否则 val 指标不可信。
    """
    return transforms.Compose([
        transforms.Resize(RESIZE_SHORT, interpolation=InterpolationMode.BILINEAR),
        transforms.CenterCrop(IMG_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def build_train_transform() -> transforms.Compose:
    """训练集使用的增强预处理（仅训练集可用）。

    水下图像特点：光照不均、浑浊、目标常偏离中心。
    因此加入适度仿射 + 颜色抖动；但【不做水平翻转的镜像语义假设】——
    鱼类左右对称，翻转是安全的，故保留。
    """
    return transforms.Compose([
        transforms.Resize(RESIZE_SHORT, interpolation=InterpolationMode.BILINEAR),
        transforms.RandomResizedCrop(
            IMG_SIZE,
            scale=TRAIN_CROP_SCALE,
            ratio=(0.875, 1.143),          # ±1/8 宽高比抖动
            interpolation=InterpolationMode.BILINEAR,
        ),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomRotation(TRAIN_ROTATION_DEG, interpolation=InterpolationMode.BILINEAR),
        transforms.ColorJitter(
            brightness=TRAIN_COLOR_JITTER[0],
            contrast=TRAIN_COLOR_JITTER[1],
            saturation=TRAIN_COLOR_JITTER[2],
            hue=TRAIN_COLOR_JITTER[3],
        ),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


# ---------------- 推理侧统一入口 ----------------

_EVAL_TF = None


def get_eval_transform() -> transforms.Compose:
    """进程内单例，避免每次请求都重建 transform 对象。"""
    global _EVAL_TF
    if _EVAL_TF is None:
        _EVAL_TF = build_eval_transform()
    return _EVAL_TF


def load_image_rgb(source) -> Image.Image:
    """把任意来源（路径 / bytes / file-like）读成 RGB 的 PIL Image。

    cv2 读入为 BGR，必须经此函数转 RGB；直接喂给 torchvision 会得到错误结果。
    """
    if isinstance(source, Image.Image):
        img = source
    elif isinstance(source, (bytes, bytearray)):
        img = Image.open(io.BytesIO(source))
    elif hasattr(source, 'read'):
        img = Image.open(source)
    elif isinstance(source, str):
        img = Image.open(source)
    else:
        raise TypeError(f'不支持的图像来源类型: {type(source)!r}')

    # 统一到 RGB：处理灰度、RGBA、调色板等
    if img.mode != 'RGB':
        img = img.convert('RGB')
    return img


def preprocess_for_inference(source) -> torch.Tensor:
    """推理入口：任意来源 → (1, 3, 224, 224) float32 张量。

    这是后端服务唯一允许调用的预处理函数。
    """
    img = load_image_rgb(source)
    tf = get_eval_transform()
    tensor = tf(img)                       # (3, 224, 224)
    return tensor.unsqueeze(0).contiguous()  # (1, 3, 224, 224)


def denormalize(tensor: torch.Tensor) -> torch.Tensor:
    """反归一化回 [0,1]，用于把预处理结果可视化回看（调试用）。"""
    mean = torch.tensor(IMAGENET_MEAN).view(-1, 1, 1)
    std = torch.tensor(IMAGENET_STD).view(-1, 1, 1)
    return (tensor.cpu() * std + mean).clamp(0, 1)


if __name__ == '__main__':
    import os
    import sys

    print('预处理口径')
    print(f'  输入尺寸      : {IMG_SIZE}×{IMG_SIZE}')
    print(f'  短边缩放      : {RESIZE_SHORT}')
    print(f'  归一化 mean   : {IMAGENET_MEAN}')
    print(f'  归一化 std    : {IMAGENET_STD}')
    print()

    # 用数据集里真实的一张图做冒烟测试
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import DATA_ROOT            # 可移植：由仓库位置推导
    from species_meta import SPECIES
    sp = SPECIES[idx]
    d = os.path.join(DATA_ROOT, sp.dir_name)
    if not os.path.isdir(d):
        print(f'  ⚠ 数据集目录不存在，跳过样例冒烟：{d}')
        print('     请按 README「数据集准备」章节放置 fish_image23/ 后重试。')
        raise SystemExit(0)
    fname = sorted(os.listdir(d))[0]
    fp = os.path.join(d, fname)

    print(f'  样例图        : {sp.dir_name}/{fname}')
    with Image.open(fp) as raw:
        print(f'  原始尺寸      : {raw.size} mode={raw.mode}')

    t = preprocess_for_inference(fp)
    print(f'  张量形状      : {tuple(t.shape)} dtype={t.dtype}')
    print(f'  张量统计      : min={t.min():.4f} max={t.max():.4f} mean={t.mean():.4f}')
    print()
    print('  ✓ 预处理模块就绪')
