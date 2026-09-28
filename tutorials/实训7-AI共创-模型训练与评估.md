# 实训 7 基于 AI 共创的海瞳鱼鉴模型训练与评估

## 一、实训目标

1. 掌握海洋鱼类图像数据集的盘点、目录结构与类别索引约定（class_index = N - 1）
2. 理解训练 / 推理双流水线预处理一致性的硬性要求（逐元素相同，容差 0）及其工程实现
3. 学会使用 ResNet18 迁移学习完成海瞳鱼鉴分类模型训练（差分学习率、加权采样、余弦退火、早停）
4. 能够运行对照实验（M1 / M2 / C1 / C2 / C3 / S1）并解读评估指标
5. 掌握 OOD 网图评估与混合微调流程，理解模型从 Top-1 32.26% 提升到 82.80% 的改进路径

## 二、实训内容

### 1. 背景知识

- **迁移学习**：海瞳鱼鉴以 PyTorch 官方 `ResNet18_Weights.IMAGENET1K_V1` 为初始化权重，仅替换最后的全连接头为 `Dropout(0.3) + Linear(512, 23)`，在自有鱼类数据集上微调。迁移学习能显著缓解小样本与长尾问题。
- **长尾失衡（核心风险 R-D-01）**：`fish_image23` 共 27,324 张 `.png`、23 类，头部 4 类占据 82.1% 样本，尾部类样本极少，直接训练会导致头部过自信、尾部召回低。应对手段有四：加权随机采样（`WeightedRandomSampler`）、类别加权损失（power=0.5）、标签平滑（label_smoothing=0.1）、差分学习率（分类头 1e-3 / 主干 1e-4）。
- **预处理一致性（PRD §10.4.2）**：训练与推理两条流水线必须产出逐元素相同的张量，容差 0。工程上把预处理的唯一定义收敛到 `ml/dataset/preprocess.py` 的 `build_eval_transform()` / `build_train_transform()`，训练侧与推理侧一律从此处取，禁止各自 `new` 一个 transform；配套单测 `test_preprocess_parity.py` 用同一张图分别走两条路径断言 bitwise 相等。
- **早停指标**：以宏观 F1（macro_f1）为准，而非准确率（长尾下准确率会被头部拉高而掩盖尾部问题）。`early_stop_patience=7`、`early_stop_metric='macro_f1'`。

### 2. 项目结构

```
E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\
└── ml\
    ├── config.py                  # TrainConfig + 设备/目录
    ├── species_meta.py            # NUM_CLASSES / INDEX_TO_CN / INDEX_TO_SCI
    ├── dataset\
    │   ├── preprocess.py          # 双流水线唯一入口
    │   ├── fish_dataset.py        # build_loaders / load_split / make_class_weights
    │   └── ...
    ├── training\
    │   └── train.py               # ResNet18 迁移学习主流程
    ├── models\                    # 产出 best.pt（M1_main_224 / M1_ood_tuned 等）
    └── reports\                   # run_config.json / metrics.json / confusion.png
```

### 3. 数据集与训练关键参数

| 项目 | 取值 |
|------|------|
| 数据集名 | fish_image23 |
| 图片总量 | 27,324 张 `.png` |
| 类别数 | 23 |
| 类别索引约定 | `class_index = N - 1`（N 为 1 基序号） |
| 长尾头部 | 4 类占 82.1% |
| 输入尺寸 | 224 × 224 |
| 架构 | resnet18（pretrained=True） |
| 训练硬件 | RTX 4060 8GB / CUDA 12.6 / torch 2.14.0+cu126 |
| 训练时长 | 约 17.3 分钟 |

## 三、实训步骤

### 步骤 1：与 AI 共创完成数据集盘点与预处理

**操作命令：**

打开 AI 对话窗口，输入以下指令，让 AI 协助完成数据集盘点与预处理一致性设计：

```text
请协助我对海瞳鱼鉴的 fish_image23 数据集做盘点（27,324 张 .png、23 类、
class_index = N-1、头部 4 类占 82.1%），并设计训练/推理双流水线预处理，
要求两条路径产出逐元素相同张量（容差 0），给出 ml/dataset/preprocess.py 实现。
```

**验证方法：**

```powershell
# 确认数据集根目录存在
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml\..\..\fish_image23\fish_image"
# 预期输出: True

# 确认预处理模块存在且包含唯一定义入口
Select-String -Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml\dataset\preprocess.py" `
  -Pattern "build_eval_transform|build_train_transform|ToTensor|Normalize"
# 预期输出: 命中对应定义行
```

**成功标志：**
- AI 输出数据集盘点报告与 `preprocess.py` 实现
- 模块中仅 `build_eval_transform()` / `build_train_transform()` 两个变换构造函数
- 推理路径无随机性（无 ColorJitter / RandomErasing / 随机翻转）

### 步骤 2：确认双流水线预处理一致性（容差 0）

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml"
python -c @"
from dataset.preprocess import build_eval_transform, build_train_transform
from PIL import Image
import torch
img = Image.open(r'..\fish_image23\fish_image\0\sample.png').convert('RGB')
# 推理路径（确定性）
t_eval = build_eval_transform()(img)
# 训练路径在同一 seed 下验证分支应与推理一致（单测已覆盖 bitwise）
print('eval tensor shape:', tuple(t_eval.shape), 'dtype:', t_eval.dtype)
print('mean near ImageNet:', float(t_eval.mean()))
"@
```

> 注意：训练路径含随机增强，仅验证分支（无随机）需与推理 bitwise 相等。真正的断言由 `test_preprocess_parity.py` 完成。

**验证方法：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml"
python -m pytest dataset/test_preprocess_parity.py -v 2>&1 | Select-String -Pattern "passed|failed"
# 预期输出: passed，无 failed
```

**成功标志：**
- 推理张量为 NCHW / float32 / RGB，形状 (3, 224, 224)
- 归一化使用 ImageNet 统计量 (0.485,0.456,0.406)/(0.229,0.224,0.225)
- 一致性单测通过，两条流水线逐元素相同，容差 0

### 步骤 3：确认训练配置与设备

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml"
python config.py
```

**验证方法：**

```powershell
python config.py 2>&1 | Select-String -Pattern "设备|CUDA|torch|num_classes|img_size|arch|pretrained"
# 预期输出: 设备: NVIDIA GeForce RTX 4060 | 显存 8.0 GB | CUDA 12.6 | torch 2.14.0+cu126
```

**成功标志：**
- 设备摘要显示 `RTX 4060`、显存 8.0 GB、CUDA 12.6、torch 2.14.0+cu126
- 训练配置打印 `num_classes=23`、`img_size=224`、`arch=resnet18`、`pretrained=True`

### 步骤 4：启动模型训练（ResNet18 迁移学习）

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml"
python training/train.py --run-name resnet18_baseline
# 快速冒烟（可选）
python training/train.py --smoke
```

**验证方法：**

```powershell
# 训练开始后观察首个 epoch 的 loss 下降与设备使用
Get-Process -Name python | Select-Object -First 1
# 预期输出: 显示 python 进程（占用 GPU 显存）

# 训练完成后检查产出
Test-Path "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml\models\resnet18_baseline\best.pt"
# 预期输出: True
```

**成功标志：**
- 训练在 RTX 4060 上约 17.3 分钟完成（30 epoch，早停可能在 patience=7 内提前收敛）
- 启用混合精度（bf16），差分学习率生效（分类头 1e-3 / 主干 1e-4）
- `models/resnet18_baseline/` 下生成 `best.pt` 与 `run_config.json`

### 步骤 5：运行对照实验（M1 / M2 / C1 / C2 / C3 / S1）

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml"
# M1 基线（加权采样 + 类别加权 + 标签平滑）
python training/train.py --run-name M1_main_224
# M2 关闭类别加权（检验采样器是否足够）
python training/train.py --run-name M2_no_class_weight --no-class-weight
# C1 关闭加权采样
python training/train.py --run-name C1_no_sampler --no-sampler
# C2 关闭标签平滑
python training/train.py --run-name C2_no_label_smooth --label-smoothing 0
# C3 关闭混合精度
python training/train.py --run-name C3_no_amp --no-amp
# S1 小分辨率 / 小批次对照
python training/train.py --run-name S1_small --img-size 160 --batch-size 32
```

**验证方法：**

```powershell
# 逐一核对各 run 的指标文件
Get-ChildItem "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml\reports" -Recurse -Filter "metrics.json" | Select-Object FullName
# 预期输出: 列出 M1..S1 各自的 metrics.json
```

**成功标志：**
- 六个 run 各自产出 `metrics.json`
- 对照结论：加权采样 + 类别加权 + 标签平滑组合（M1）在 macro_f1 上最优，证明长尾应对有效

### 步骤 6：评估指标解读与门槛判定

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml"
python -c @"
import json, glob
for f in sorted(glob.glob('reports/*/metrics.json')):
    m = json.load(open(f))
    print(f.split('\\')[-2], 'acc=%.4f' % m['accuracy'], 'macro_f1=%.4f' % m['macro_f1'])
"@
```

**验证方法：**

```powershell
# 重点查看 M1 主模型
python -c "import json; m=json.load(open('reports/M1_main_224/metrics.json')); print(m['accuracy'], m['macro_f1'])"
# 预期输出: 0.9963 0.9678
```

**成功标志：**
- M1 主模型：`accuracy = 0.9963`、`macro_f1 = 0.9678`
- 通过 PRD §4 硬指标门槛：`acc ≥ 85%`（0.9963 满足）且 `macro_f1 ≥ 0.82`（0.9678 满足）
- 训练监控以 macro_f1 为准，避免头部类掩盖尾部问题

### 步骤 7：OOD 网图评估与混合微调

**操作命令：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml"
# 先评估 OOD（网图 / 非真实拍摄）基线
python training/eval_ood.py --model models/M1_main_224/best.pt --split ood
# 混合微调：加入网图样本进行混合训练得到 M1_ood_tuned
python training/train.py --run-name M1_ood_tuned --extra-data ood_web_images
```

**验证方法：**

```powershell
python -c "import json; m=json.load(open('reports/M1_ood_tuned/metrics_ood.json')); print('ood_top1=%.4f' % m['top1'])"
# 预期输出: ood_top1=0.8280
```

**成功标志：**
- OOD 网图 Top-1 从 `32.26%` 提升到 `82.80%`
- 混合微调后模型在真实拍摄与网图两类分布上均保持可用
- 生产默认指向 `M1_ood_tuned/best.pt`，回滚可指回 `M1_main_224/best.pt`

## 四、验证清单

完成所有步骤后，请确认以下验证项：

| 验证项 | 验证方法 | 预期结果 |
|--------|----------|----------|
| 数据集存在 | `Test-Path fish_image` | True |
| 类别数 | 读取 species_meta | 23 类 |
| 预处理入口唯一 | `Select-String preprocess.py` | 仅 eval/train 两函数 |
| 双流水线一致性 | `pytest test_preprocess_parity.py` | passed，容差 0 |
| 设备可用 | `python config.py` | RTX 4060 / CUDA 12.6 / torch 2.14.0+cu126 |
| 训练产出 | `Test-Path models/resnet18_baseline/best.pt` | True |
| 主模型指标 | 读取 metrics.json | acc=0.9963, macro_f1=0.9678 |
| 门槛判定 | 对比 PRD §4 | acc≥85% 且 macro_f1≥0.82 通过 |
| 对照实验 | 各 run 的 metrics.json | M1..S1 六组齐全 |
| OOD 提升 | 读取 ood metrics | Top-1 32.26%→82.80% |

## 五、故障排除

### 问题 1：训练报 CUDA out of memory

**现象：** 启动 `train.py` 后很快报 `CUDA out of memory`，进程中断。

**解决方案：**

```powershell
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml"
# 降低批次大小（RTX 4060 8GB 下 64 通常可跑，若不行降到 32）
python training/train.py --run-name M1_main_224 --batch-size 32
# 仍不足可关闭混合精度或减小 img_size
python training/train.py --run-name M1_main_224 --no-amp --img-size 160
```

### 问题 2：预处理一致性单测失败（容差不为 0）

**现象：** `test_preprocess_parity.py` 报张量不相等，或数值差超过容差。

**解决方案：**

```powershell
# 检查推理路径是否被误加了随机增强
Select-String -Path "ml/dataset/preprocess.py" -Pattern "ColorJitter|RandomErasing|RandomHorizontalFlip"
# 推理函数 build_eval_transform 不应含上述随机项；
# 若含，移除以保证确定性（训练函数 build_train_transform 才允许）
```

### 问题 3：macro_f1 远低于准确率（长尾未处理）

**现象：** 准确率很高（如 0.95+）但 macro_f1 不达标（< 0.82），尾部类几乎全错。

**解决方案：**

```powershell
# 确认加权采样与类别加权已开启（默认开启）
python -c "from config import TrainConfig; c=TrainConfig(); print(c.weighted_sampler, c.class_weight_power, c.label_smoothing)"
# 预期输出: True 0.5 0.1；若为 False/0，恢复默认后重训
python training/train.py --run-name M1_main_224
```

### 问题 4：torch 未使用 GPU（CUDA 不可用）

**现象：** `python config.py` 显示设备为 CPU，训练极慢。

**解决方案：**

```powershell
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
# 预期输出: 2.14.0+cu126 12.6 True
# 若为 False，重装 cu126 版本：
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

### 问题 5：OOD 微调后真实拍摄分布指标下降

**现象：** 混合微调后网图 Top-1 提升，但真实拍摄 acc / macro_f1 回落。

**解决方案：**

```powershell
# 控制 OOD 混入比例与学习率，避免灾难性遗忘；回滚到主模型
# 生产默认模型路径改回主模型
$env:SEATONG_MODEL_PATH = "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml\models\M1_main_224\best.pt"
```

## 六、参考代码

### 完整目录结构

```
E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml\
├── config.py                  # TrainConfig + pick_device/device_summary/ensure_dirs
├── species_meta.py            # NUM_CLASSES=23, INDEX_TO_CN, INDEX_TO_SCI
├── dataset\
│   ├── preprocess.py          # build_eval_transform / build_train_transform
│   ├── fish_dataset.py        # build_loaders / load_split / make_class_weights
│   └── test_preprocess_parity.py
├── training\
│   └── train.py               # build_model / run_epoch / main
├── models\                    # M1_main_224 / M1_ood_tuned / ...
│   └── <run_name>\best.pt
└── reports\<run_name>\
    ├── run_config.json
    ├── metrics.json
    └── confusion.png
```

### 训练配置关键字段（config.py 节选）

```python
@dataclass
class TrainConfig:
    num_classes: int = 23
    img_size: int = 224
    arch: str = 'resnet18'
    pretrained: bool = True          # 迁移学习：加载 ImageNet 权重
    dropout: float = 0.3
    epochs: int = 30
    batch_size: int = 64
    lr_head: float = 1e-3            # 新分类头：大学习率
    lr_backbone: float = 1e-4        # 预训练主干：小学习率（差分学习率）
    label_smoothing: float = 0.1
    scheduler: str = 'cosine'
    early_stop_patience: int = 7
    early_stop_metric: str = 'macro_f1'
    weighted_sampler: bool = True    # 反频率采样应对长尾
    class_weight_power: float = 0.5
    amp: bool = True
    amp_dtype: str = 'bf16'
    target_accuracy: float = 0.85
    target_macro_f1: float = 0.82
```

### 预处理唯一定义（preprocess.py 节选）

```python
IMG_SIZE = 224
RESIZE_SHORT = 256
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def build_eval_transform():
    """推理/验证/测试使用的确定性预处理（与训练验证分支 bitwise 相等）。"""
    return transforms.Compose([
        transforms.Resize(RESIZE_SHORT, interpolation=InterpolationMode.BILINEAR),
        transforms.CenterCrop(IMG_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def build_train_transform():
    """训练集使用的增强预处理（仅训练集可用，含随机性）。"""
    return transforms.Compose([
        transforms.Resize(RESIZE_SHORT, interpolation=InterpolationMode.BILINEAR),
        transforms.RandomResizedCrop(IMG_SIZE, scale=(0.7, 1.0), ratio=(0.875, 1.143)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomRotation(12, interpolation=InterpolationMode.BILINEAR),
        transforms.ColorJitter(0.2, 0.2, 0.2, 0.03),
        transforms.ToTensor(),
        transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])
```

### 常用命令

```powershell
# 查看设备与配置
cd "E:\基于CNN的海洋鱼类图像分类系统-海瞳鱼鉴\01.code\seatong\ml"
python config.py

# 基线训练
python training/train.py --run-name M1_main_224

# 冒烟 / 对照
python training/train.py --smoke
python training/train.py --run-name M2_no_class_weight --no-class-weight
python training/train.py --run-name C1_no_sampler --no-sampler

# 预处理一致性单测
python -m pytest dataset/test_preprocess_parity.py -v

# OOD 评估与混合微调
python training/eval_ood.py --model models/M1_main_224/best.pt --split ood
python training/train.py --run-name M1_ood_tuned --extra-data ood_web_images
```

### 对照实验说明

| 实验 | 差异点 | 目的 |
|------|--------|------|
| M1 | 基线（采样+加权+平滑） | 主模型，acc=0.9963 / macro_f1=0.9678 |
| M2 | 关闭类别加权 | 检验加权采样是否足够 |
| C1 | 关闭加权采样 | 检验类别加权损失必要性 |
| C2 | 关闭标签平滑 | 检验头部过自信缓解效果 |
| C3 | 关闭混合精度 | 检验 bf16 对指标/速度影响 |
| S1 | 小分辨率/小批次 | 轻量部署可行性对照 |

### 评估指标门槛（PRD §4）

| 指标 | 门槛 | M1 实测 |
|------|------|---------|
| accuracy | ≥ 85% | 99.63% |
| macro_f1 | ≥ 0.82 | 0.9678 |
| OOD Top-1（网图） | 提升 | 32.26% → 82.80% |
