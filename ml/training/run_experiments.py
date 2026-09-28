# -*- coding: utf-8 -*-
"""批量训练调度 —— 一次跑多组对比实验

因为单轮仅 ~3.6 分钟，30 轮 ~107 分钟，有条件用"实跑对比"代替"拍脑袋选参数"。
本脚本按顺序跑多组配置，每组独立落盘，最后汇总成对比表。

对比维度（针对已识别的两个真实问题）：
  · 输入尺寸：224（ImageNet 惯例） vs 160（贴合数据实际分辨率）
  · 长尾策略：WeightedRandomSampler vs 类别加权损失 vs 两者叠加
  · batch_size：64 vs 256（显存仅用 0.96GB，有充足余量）

用法：
    python run_experiments.py --list                 # 列出全部实验
    python run_experiments.py --only A1 A2           # 只跑指定实验
    python run_experiments.py                        # 跑全部
"""

import argparse
import io
import json
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))                 # ml/  → 可移植根路径解析
from config import MODELS_DIR, REPORTS_DIR  # noqa: E402

TRAIN_PY = os.path.join(_HERE, 'train.py')

# 实验定义：(代号, 说明, 额外 CLI 参数)
#
# 【2026-09-21 正式跑完 6 组后的结论修订 —— 原假设被推翻】
#
# 原计划依据「1 轮预跑」收窄了实验范围，并写下两条假设。正式实验（77.3 分钟）结果如下：
#   假设①「采样器 + 类别加权双重补偿有害」→【不成立】。C1 全量宏观 F1 0.9641 为六组第 5 名，
#        无断崖式劣化；其特征是偏向召回（macro R 0.9878 六组最高，macro P 0.9512 六组最低）。
#        原「1 轮时 F1 仅 0.61」应为模型未收敛的暂态，不可作结论。
#   假设②「输入 224 > 160」→【不成立】。S1(160) 全量 0.9837 反而第一，但该优势全部来自
#        8 个仅 27 张图的极小类；剔除后 S1 跌至第 6（垫底），M1 升至第 1（0.9901）。
#
# 根本问题：宏观 F1 被极小样本类主导。9 个类测试样本 <10 张（最少 2 张），
# 单个 2 样本类的判定翻转即造成 0.0435 波动，而**六组配置极差仅 0.0244**。
# → 现有测试集无法支撑组间细微差异的选型，详见 docs/海瞳鱼鉴-M2对照实验分析报告.md
#
# 稳健口径（剔除 n<=5 的 8 类，保留 14 类 / 覆盖 98.7% 样本）下的结论：
#   · 采样器主效应 −0.0019、类别加权主效应 −0.0024 —— 两个长尾策略均无正收益
#   · M1 稳健值 0.9901 为六组最高 → 维持 M1 为交付模型
EXPERIMENTS: list[tuple[str, str, list[str]]] = [
    ('M1', '主方案：224 + 仅采样器 + bs256 + 30 轮（预期交付模型）',
     ['--run-name', 'M1_main_224', '--batch-size', '256', '--epochs', '30',
      '--no-class-weight']),

    ('M2', '主方案延长：50 轮（看是否还有提升空间）',
     ['--run-name', 'M2_main_224_e50', '--batch-size', '256', '--epochs', '50',
      '--no-class-weight']),

    ('C1', '对照：224 + 采样器 + 类别加权（原假设"双重补偿有害"，实测证伪：呈偏召回特征）',
     ['--run-name', 'C1_double_compensate', '--batch-size', '256', '--epochs', '15']),

    ('C2', '对照：224 + 仅类别加权 + 15 轮（原假设"采样器优于损失加权"，实测两者均无正收益）',
     ['--run-name', 'C2_loss_only', '--batch-size', '256', '--epochs', '15',
      '--no-sampler']),

    ('C3', '对照：224 + 无任何长尾处理 + 15 轮（长尾基线；实测亦达标，稳健口径 0.9850 第 2）',
     ['--run-name', 'C3_no_tail_handling', '--batch-size', '256', '--epochs', '15',
      '--no-sampler', '--no-class-weight']),

    ('S1', '敏感性：输入 160 + 仅采样器（全量口径虚高第一，剔除极小组后垫底 —— 反例样本）',
     ['--run-name', 'S1_img160', '--img-size', '160', '--batch-size', '256',
      '--epochs', '15', '--no-class-weight']),
]


def read_report(name: str) -> dict | None:
    p = os.path.join(MODELS_DIR, name, 'report.json')
    if not os.path.exists(p):
        return None
    try:
        with io.open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--only', nargs='*', default=None)
    ap.add_argument('--summarize-only', action='store_true')
    args = ap.parse_args()

    if args.list:
        print('可用实验:')
        for code, desc, cli in EXPERIMENTS:
            name = cli[cli.index('--run-name') + 1]
            done = '✓ 已完成' if read_report(name) else '  待运行'
            print(f'  [{code}] {done}  {desc}')
            print(f'        运行名 {name}')
        return 0

    todo = [(c, d, cli) for c, d, cli in EXPERIMENTS
            if args.only is None or c in args.only]

    if not args.summarize_only:
        print('=' * 80)
        print(f'批量实验：共 {len(todo)} 组')
        print('=' * 80)
        t_all = time.time()
        for i, (code, desc, cli) in enumerate(todo, 1):
            name = cli[cli.index('--run-name') + 1]
            print()
            print('─' * 80)
            print(f'  [{i}/{len(todo)}] 实验 {code}：{desc}')
            print('─' * 80)
            if read_report(name):
                print(f'  已存在结果，跳过（如需重跑请先删除 {name} 目录）')
                continue
            t0 = time.time()
            r = subprocess.run([sys.executable, TRAIN_PY] + cli,
                               cwd=os.path.dirname(TRAIN_PY))
            dt = (time.time() - t0) / 60
            print(f'  实验 {code} 结束，耗时 {dt:.1f} 分钟，返回码 {r.returncode}')
        print()
        print(f'全部实验完成，总耗时 {(time.time()-t_all)/60:.1f} 分钟')

    # ---- 汇总 ----
    print()
    print('=' * 80)
    print('实验结果对比')
    print('=' * 80)
    rows = []
    for code, desc, cli in EXPERIMENTS:
        name = cli[cli.index('--run-name') + 1]
        rep = read_report(name)
        if not rep:
            rows.append((code, name, None))
            continue
        rows.append((code, name, rep))

    hdr = (f'  {"代号":<5}{"运行名":<18}{"输入":>5}{"bs":>5}{"最优轮":>7}'
           f'{"准确率":>9}{"宏观F1":>9}{"加权F1":>9}  {"达标":<8}')
    print(hdr)
    print('  ' + '-' * 76)
    for code, name, rep in rows:
        if rep is None:
            print(f'  {code:<5}{name:<18}{"—":>5}{"—":>5}{"—":>7}{"未完成":>9}')
            continue
        tm = rep['test_metrics']
        cfg = rep['config']
        met = rep['targets_met']
        mark = ('双达标' if met['accuracy'] and met['macro_f1']
                else ('仅准确率' if met['accuracy'] else ('仅F1' if met['macro_f1'] else '未达标')))
        print(f'  {code:<5}{name:<18}{cfg["img_size"]:>5}{cfg["batch_size"]:>5}'
              f'{rep["best_epoch"]:>7}{tm["accuracy"]:>9.4f}{tm["macro_f1"]:>9.4f}'
              f'{tm["weighted_f1"]:>9.4f}  {mark:<8}')

    print()
    print(f'  硬指标：准确率 ≥0.85 / 宏观 F1 ≥0.82')
    best = [r for r in rows if r[2]]
    if best:
        top = max(best, key=lambda r: r[2]['test_metrics']['macro_f1'])
        print(f'  宏观 F1 最高：{top[0]} ({top[1]}) = '
              f'{top[2]["test_metrics"]["macro_f1"]:.4f}')

    # 落盘汇总
    os.makedirs(REPORTS_DIR, exist_ok=True)
    summary = [{'code': c, 'run_name': n,
                'config': r['config'] if r else None,
                'test_metrics': r['test_metrics'] if r else None,
                'best_epoch': r['best_epoch'] if r else None,
                'targets_met': r['targets_met'] if r else None}
               for c, n, r in rows]
    sp = os.path.join(REPORTS_DIR, 'experiments_summary.json')
    with io.open(sp, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(f'  汇总已写入 {sp}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
