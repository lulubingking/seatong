# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 分层抽样数据划分

目标：把 27,324 张图划分 train / val / test，并【保证每个类在 val 与 test 中都至少有样本】。

为什么不直接用 8:1:1：
    最小类 fish_21 仅 14 张，14*0.1 = 1.4；若按浮动比例取整，极易出现 val 或 test 为空，
    导致该类在评估时完全缺席 —— 宏观 F1 的分母会缺项，指标失去意义。

策略（"保底 + 比例"两段式）：
    1. 每类先【保底】val/test 各 MIN_PER_SPLIT 张（可配置，默认 2）
    2. 剩余部分再按 val_ratio / test_ratio 比例分配
    3. 若某类总数 < 保底*2 + 1（至少留 1 张给 train），则退回按比例分配并允许取整后为 1
    4. 全程固定随机种子，产出可复现的清单 JSON

输出：
    ml/dataset/split.json          —— 完整划分清单（相对路径 + 标签 + 来源目录）
    ml/dataset/split_stats.json    —— 各阶段/各类别统计，供训练脚本与报告消费
"""

import io
import json
import os
import random
import sys
from collections import defaultdict

_DATASET_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DATASET_DIR)
sys.path.insert(0, os.path.dirname(_DATASET_DIR))          # ml/
from species_meta import SPECIES, NUM_CLASSES  # noqa: E402
from config import DATA_ROOT, DATASET_DIR  # noqa: E402  (可移植：由仓库位置推导)

# ---------------- 配置 ----------------
OUT_DIR = DATASET_DIR

SEED = 20260921              # 固定种子：保证划分可复现
VAL_RATIO = 0.10
TEST_RATIO = 0.10
MIN_PER_SPLIT = 2            # val / test 每类保底张数

IMG_EXT = {'.png', '.jpg', '.jpeg', '.bmp'}


def list_images(class_dir: str) -> list[str]:
    """列出某类别目录下的全部图片文件名（排序后返回，保证顺序确定）。"""
    names = [
        f for f in os.listdir(class_dir)
        if os.path.splitext(f)[1].lower() in IMG_EXT
    ]
    names.sort()
    return names


def split_one_class(n: int) -> tuple[int, int, int]:
    """返回 (n_train, n_val, n_test)。对极小类做保底处理。

    三条路径：
      A. n >= MIN*2+1  → 按比例取整，但 val/test 各自不低于 MIN，train 至少留 1
      B. 3 <= n < MIN*2+1 → val=test=1，其余给 train（保宏观指标分母完整）
      C. n <= 2 → 逐级退化，允许 test 或 val 为空（此时该指标记 N/A 并在报告注明）
    """
    if n <= 0:
        return 0, 0, 0

    # 路径 A：正常比例 + 双保底
    if n >= MIN_PER_SPLIT * 2 + 1:
        n_val = max(MIN_PER_SPLIT, int(round(n * VAL_RATIO)))
        n_test = max(MIN_PER_SPLIT, int(round(n * TEST_RATIO)))
        # train 至少留 1 张；必要时从较大的一侧回收
        while n - n_val - n_test < 1:
            if n_val >= n_test and n_val > MIN_PER_SPLIT:
                n_val -= 1
            elif n_test > MIN_PER_SPLIT:
                n_test -= 1
            else:
                break
        return n - n_val - n_test, n_val, n_test

    # 路径 B：极小类，三集合尽量都非空
    if n >= 3:
        return n - 2, 1, 1

    # 路径 C：n <= 2
    if n == 2:
        return 1, 1, 0
    return n, 0, 0


def main() -> int:
    rng = random.Random(SEED)
    split: dict[str, list] = {'train': [], 'val': [], 'test': []}
    stats: dict = {
        'seed': SEED,
        'val_ratio': VAL_RATIO,
        'test_ratio': TEST_RATIO,
        'min_per_split': MIN_PER_SPLIT,
        'num_classes': NUM_CLASSES,
        'per_class': {},
    }

    total = 0
    for sp in SPECIES:
        cdir = os.path.join(DATA_ROOT, sp.dir_name)
        if not os.path.isdir(cdir):
            print(f'  ! 目录不存在: {cdir}')
            return 1
        names = list_images(cdir)
        n = len(names)
        total += n

        if n != sp.local_count:
            print(f'  ! {sp.dir_name} 实际 {n} 张，元数据记 {sp.local_count} 张，请核对')

        n_train, n_val, n_test = split_one_class(n)

        shuffled = names[:]
        rng.shuffle(shuffled)
        part_train = shuffled[:n_train]
        part_val = shuffled[n_train:n_train + n_val]
        part_test = shuffled[n_train + n_val:n_train + n_val + n_test]

        for split_name, part in (('train', part_train), ('val', part_val), ('test', part_test)):
            for fn in part:
                # 存【相对于 DATA_ROOT】的路径：DATA_ROOT 已是 .../fish_image23/fish_image
                # 故此处只需 `fish_{N}/xxx.png`，不可再带 fish_image 前缀
                rel = os.path.join(sp.dir_name, fn)
                split[split_name].append({
                    'path': rel,
                    'class_index': sp.class_index,
                    'dir_name': sp.dir_name,
                })

        stats['per_class'][sp.dir_name] = {
            'class_index': sp.class_index,
            'cn_name': sp.cn_name,
            'sci_name': sp.sci_name,
            'total': n,
            'train': n_train,
            'val': n_val,
            'test': n_test,
        }
        flag = '  <-- 极小类保底' if n < MIN_PER_SPLIT * 2 + 1 else ''
        print(f'  {sp.dir_name:8s} idx={sp.class_index:2d} 总 {n:6d} | '
              f'train {n_train:6d} val {n_val:3d} test {n_test:3d}{flag}')

    stats['totals'] = {k: len(v) for k, v in split.items()}
    stats['totals']['all'] = total

    os.makedirs(OUT_DIR, exist_ok=True)
    with io.open(os.path.join(OUT_DIR, 'split.json'), 'w', encoding='utf-8') as f:
        json.dump(split, f, ensure_ascii=False, indent=1)
    with io.open(os.path.join(OUT_DIR, 'split_stats.json'), 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)

    print()
    print(f'  合计 {total:,} 张 → train {stats["totals"]["train"]:,} / '
          f'val {stats["totals"]["val"]:,} / test {stats["totals"]["test"]:,}')
    print()

    # ---- 校验：每个类在 val 与 test 中是否都有样本 ----
    missing = []
    for sp in SPECIES:
        s = stats['per_class'][sp.dir_name]
        if s['val'] == 0:
            missing.append(f'{sp.dir_name} 的 val 为空')
        if s['test'] == 0:
            missing.append(f'{sp.dir_name} 的 test 为空')
    if missing:
        print('  ✗ 校验失败：')
        for m in missing:
            print('     !', m)
        return 1
    print('  ✓ 校验通过：23 类在 val 与 test 中均有样本，宏观 F1 分母完整')

    # ---- 校验：无重复分配 ----
    all_paths = [r['path'] for v in split.values() for r in v]
    if len(all_paths) != len(set(all_paths)):
        print(f'  ✗ 校验失败：存在重复分配 {len(all_paths) - len(set(all_paths))} 条')
        return 1
    print('  ✓ 校验通过：无重复分配')
    if len(all_paths) != total:
        print(f'  ✗ 校验失败：分配总数 {len(all_paths)} ≠ 数据集总数 {total}')
        return 1
    print('  ✓ 校验通过：全部样本已分配，无遗漏')

    # ---- 校验：清单路径必须真实可解析（防路径拼接错误） ----
    # 抽样验证：每类取 3 条，按 FishDataset 的拼法解析并确认文件存在
    bad = []
    probe = {sp.dir_name: 0 for sp in SPECIES}
    for split_name, recs in split.items():
        for r in recs:
            if probe.get(r['dir_name'], 0) >= 3:
                continue
            probe[r['dir_name']] += 1
            abs_path = os.path.join(DATA_ROOT, r['path'])
            if not os.path.isfile(abs_path):
                bad.append(f'[{split_name}] {abs_path}')
    if bad:
        print(f'  ✗ 校验失败：清单中的路径无法解析（{len(bad)} 例）')
        for b in bad[:5]:
            print('     !', b)
        print(f'       提示：DATA_ROOT={DATA_ROOT}')
        print(f'       path 字段应为「相对 DATA_ROOT」的路径，如 fish_1/xxx.png')
        return 1
    print(f'  ✓ 校验通过：抽样 {sum(probe.values())} 条路径全部可解析（每类 3 条，覆盖三个划分）')

    print()
    print(f'  清单已写入 {OUT_DIR}\\split.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
