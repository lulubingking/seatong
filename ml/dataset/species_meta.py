# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 23 类物种元数据（唯一权威来源）

本模块是 `class_index` 对齐的唯一来源，同时被以下三处消费：
  1. 训练侧 —— 生成 classes.txt、类别权重、混淆矩阵标签
  2. 后端 `species` 表 —— 物种介绍与形态习性
  3. 前端结果页 —— 展示名称与知识库文案

对齐规则（不得变更）：
  class_index = N - 1   （0 基）
  目录名     = fish_{N}  （1 基）

权威出处：Fish4Knowledge 官方 groundtruth
  https://homepages.inf.ed.ac.uk/rbf/Fish4Knowledge/GROUNDTRUTH/RECOG/
  （爱丁堡大学 R. B. Fisher 课题组）
本地数据与其编号逐类对齐的校验依据：23 类官方数与本地数【全部恰好相差 -2】
  （官方 27,370 → 本地 27,324），恒定偏差 = 编号对齐的铁证。

注意事项：
  - fish_18 官方标注仅到科级（Scaridae），文案【必须按科级描述，不得杜撰种名】
  - 拉丁学名易错拼写已按官方原文核对：
      Abudefduf vaigiensis（非 Abudefduf vaigensis）
      Neoniphon sammara（非 samara）
"""

from typing import NamedTuple


class Species(NamedTuple):
    class_index: int      # 0 基，模型输出下标
    dir_name: str         # 数据集目录名 fish_{N}
    sci_name: str         # 拉丁学名
    cn_name: str          # 中文名
    official_count: int   # Fish4Knowledge 官方 groundtruth 张数
    local_count: int      # 本地实际张数
    is_genus_level: bool  # True 表示仅到科/属级，文案不得写种名


SPECIES: list[Species] = [
    Species(0,  "fish_1",  "Dascyllus reticulatus",       "网纹宅泥鱼",     12112, 12110, False),
    Species(1,  "fish_2",  "Plectroglyphidodon dickii",   "迪克氏固曲齿鲷",  2683,  2681, False),
    Species(2,  "fish_3",  "Chromis chrysura",            "长棘光鳃鱼",      3593,  3591, False),
    Species(3,  "fish_4",  "Amphiprion clarkii",          "克氏双锯鱼",      4049,  4047, False),
    Species(4,  "fish_5",  "Chaetodon lunulatus",         "弓月蝴蝶鱼",      2534,  2532, False),
    Species(5,  "fish_6",  "Chaetodon trifascialis",      "川纹蝴蝶鱼",       190,   188, False),
    Species(6,  "fish_7",  "Myripristis kuntee",          "康德锯鳞鱼",       450,   448, False),
    Species(7,  "fish_8",  "Acanthurus nigrofuscus",      "双斑刺尾鱼",       218,   216, False),
    Species(8,  "fish_9",  "Hemigymnus fasciatus",        "横带粗唇鱼",       241,   239, False),
    Species(9,  "fish_10", "Neoniphon sammara",           "莎姆金鳞鱼",       299,   297, False),
    Species(10, "fish_11", "Abudefduf vaigiensis",        "五带豆娘鱼",        98,    96, False),
    Species(11, "fish_12", "Canthigaster valentini",      "黑马鞍鲀",         147,   145, False),
    Species(12, "fish_13", "Pomacentrus moluccensis",     "摩鹿加雀鲷",       181,   179, False),
    Species(13, "fish_14", "Zebrasoma scopas",            "黑三角倒吊鱼",      90,    88, False),
    Species(14, "fish_15", "Hemigymnus melapterus",       "黑鳍粗唇鱼",        42,    40, False),
    Species(15, "fish_16", "Lutjanus fulvus",             "黄足笛鲷",         206,   204, False),
    Species(16, "fish_17", "Scolopsis bilineata",         "双线眶棘鲈",        49,    47, False),
    Species(17, "fish_18", "Scaridae",                    "鹦嘴鱼科",          56,    54, True),   # 仅科级
    Species(18, "fish_19", "Pempheris vanicolensis",      "黑缘单鳍鱼",        29,    27, False),
    Species(19, "fish_20", "Zanclus cornutus",            "镰鱼",              21,    19, False),
    Species(20, "fish_21", "Neoglyphidodon nigroris",     "黑嘴雀鲷",          16,    14, False),
    Species(21, "fish_22", "Balistapus undulatus",        "黄纹炮弹鱼",        41,    39, False),
    Species(22, "fish_23", "Siganus fuscescens",          "褐蓝子鱼",          25,    23, False),
]

NUM_CLASSES: int = len(SPECIES)

# 类别 → class_index
DIR_TO_INDEX: dict[str, int] = {s.dir_name: s.class_index for s in SPECIES}
INDEX_TO_DIR: dict[int, str] = {s.class_index: s.dir_name for s in SPECIES}
INDEX_TO_CN: dict[int, str] = {s.class_index: s.cn_name for s in SPECIES}
INDEX_TO_SCI: dict[int, str] = {s.class_index: s.sci_name for s in SPECIES}

# fish_{N} ↔ class_index = N-1 的双向换算
def dir_name_to_class_index(dir_name: str) -> int:
    """`fish_7` → 6"""
    n = int(dir_name.split('_')[1])
    return n - 1


def class_index_to_dir_name(class_index: int) -> str:
    """6 → `fish_7`"""
    return f"fish_{class_index + 1}"


def classes_txt_lines() -> list[str]:
    """生成 classes.txt 的内容：按 class_index 升序，每行 `fish_{N}`。"""
    return [s.dir_name for s in sorted(SPECIES, key=lambda x: x.class_index)]


def official_total() -> int:
    return sum(s.official_count for s in SPECIES)


def local_total() -> int:
    return sum(s.local_count for s in SPECIES)


def verify_alignment() -> list[str]:
    """自检：编号连续性、目录换算一致性、恒定 -2 偏差。返回问题清单（空 = 通过）。"""
    problems: list[str] = []
    for i, s in enumerate(SPECIES):
        if s.class_index != i:
            problems.append(f"class_index 不连续：第 {i} 项为 {s.class_index}")
        if s.dir_name != class_index_to_dir_name(s.class_index):
            problems.append(f"目录换算不一致：{s.dir_name} vs {class_index_to_dir_name(s.class_index)}")
        if dir_name_to_class_index(s.dir_name) != s.class_index:
            problems.append(f"反向换算不一致：{s.dir_name}")
        if s.official_count - s.local_count != 2:
            problems.append(
                f"{s.dir_name} 官方-本地 偏差为 {s.official_count - s.local_count}，应为 2"
            )
    return problems


if __name__ == '__main__':
    print(f"类别数        : {NUM_CLASSES}")
    print(f"官方合计      : {official_total():,}")
    print(f"本地合计      : {local_total():,}")
    print(f"恒定偏差      : {official_total() - local_total()}")
    print()
    head4 = sorted(SPECIES, key=lambda x: -x.local_count)[:4]
    h4 = sum(s.local_count for s in head4)
    print(f"头部 4 类     : {[s.dir_name for s in head4]}")
    print(f"头部 4 类合计 : {h4:,} = {h4 / local_total() * 100:.1f}%  (核心风险 R-D-01 长尾失衡)")
    print(f"最小类        : fish_21 = 14 张")
    print(f"最频繁类基线  : {max(s.local_count for s in SPECIES) / local_total() * 100:.1f}%")
    print()
    probs = verify_alignment()
    print("对齐自检      :", "通过 ✓" if not probs else f"失败 {len(probs)} 项")
    for p in probs:
        print("   !", p)
    print()
    print("classes.txt 前 5 行:")
    for ln in classes_txt_lines()[:5]:
        print("   ", ln)
