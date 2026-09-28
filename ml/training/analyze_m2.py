# -*- coding: utf-8 -*-
"""M2 对照实验的稳健性分析 —— 生成机器可读的分析数据。

【为什么需要这个脚本】
六组实验的全量宏观 F1 排名受极小样本类主导（9 个类测试样本 <10 张，合计仅 36 张），
导致排名不可靠。本脚本产出：
  1. 全量口径 vs 稳健口径（剔除 n<=5 极小组）的排名对比
  2. 2×2 因子设计的主效应分解
  3. S1 优势的来源拆解（逐类 ΔF1）
  4. 单点敏感性（单个极小类的判定翻转对宏观 F1 的影响）

用法：
    python ml/training/analyze_m2.py
输出：
    ml/reports/m2_analysis.json
"""
from __future__ import annotations

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS = os.path.join(ROOT, 'ml', 'models')
REPORTS = os.path.join(ROOT, 'ml', 'reports')

RUNS = [
    ('M1', 'M1_main_224'),
    ('M2', 'M2_main_224_e50'),
    ('C1', 'C1_double_compensate'),
    ('C2', 'C2_loss_only'),
    ('C3', 'C3_no_tail_handling'),
    ('S1', 'S1_img160'),
]

TINY_THRESHOLD = 5     # n <= 5 视为极小组
ROBUST_MIN = 10        # 稳健口径纳入 n >= 10 的类


def _load(name):
    with io.open(os.path.join(MODELS, name, 'report.json'), encoding='utf-8') as f:
        rep = json.load(f)
    with io.open(os.path.join(MODELS, name, 'run_config.json'), encoding='utf-8') as f:
        cfg = json.load(f)
    return rep, cfg


def main() -> int:
    data = {}
    for code, name in RUNS:
        rep, cfg = _load(name)
        data[code] = {'run_name': name, 'report': rep, 'run_config': cfg}

    ref = data['M1']['report']['test_metrics']
    support = ref['per_class_support']
    n_classes = len(support)

    tiny = [i for i, n in enumerate(support) if n <= TINY_THRESHOLD]
    robust = [i for i, n in enumerate(support) if n >= ROBUST_MIN]
    tiny_imgs = sum(support[i] for i in tiny)
    robust_imgs = sum(support[i] for i in robust)
    total_imgs = sum(support)

    out = {
        'meta': {
            'total_test_images': total_imgs,
            'num_classes': n_classes,
            'tiny_class_threshold': TINY_THRESHOLD,
            'robust_class_min': ROBUST_MIN,
            'per_class_support': support,
        },

        # ---- 1. 口径差异 ----
        'tiny_classes': {
            'indices': tiny,
            'count': len(tiny),
            'images': tiny_imgs,
            'image_share': round(tiny_imgs / total_imgs, 5),
            'detail': [{'class_index': i, 'support': support[i]} for i in tiny],
        },
        'robust_scope': {
            'indices': robust,
            'count': len(robust),
            'images': robust_imgs,
            'image_share': round(robust_imgs / total_imgs, 5),
        },

        # ---- 2. 排名对比 ----
        'rankings': {},
        'factor_design': {},
        's1_advantage_decomposition': {},
        'single_point_sensitivity': {},
    }

    rows = []
    for code, _ in RUNS:
        m = data[code]['report']['test_metrics']
        c = data[code]['run_config']['config']
        rf1 = [m['per_class_f1'][i] for i in robust]
        rP = [m['per_class_precision'][i] for i in robust]
        rR = [m['per_class_recall'][i] for i in robust]
        rows.append({
            'code': code,
            'sampler': c['weighted_sampler'],
            'class_weight': c['use_class_weight'],
            'img_size': c['img_size'],
            'epochs_cap': c['epochs'],
            'best_epoch': data[code]['report']['best_epoch'],
            'epochs_run': len(data[code]['report']['history']),
            'full_macro_f1': m['macro_f1'],
            'full_accuracy': m['accuracy'],
            'full_weighted_f1': m['weighted_f1'],
            'robust_macro_f1': round(sum(rf1) / len(rf1), 6),
            'robust_macro_precision': round(sum(rP) / len(rP), 6),
            'robust_macro_recall': round(sum(rR) / len(rR), 6),
            'per_class_f1': m['per_class_f1'],
            'per_class_precision': m['per_class_precision'],
            'per_class_recall': m['per_class_recall'],
        })

    by_full = sorted(rows, key=lambda r: -r['full_macro_f1'])
    by_robust = sorted(rows, key=lambda r: -r['robust_macro_f1'])
    out['rankings'] = {
        'full_23_classes': [{'rank': i + 1, 'code': r['code'],
                             'macro_f1': round(r['full_macro_f1'], 6)}
                            for i, r in enumerate(by_full)],
        'robust_14_classes': [{'rank': i + 1, 'code': r['code'],
                               'macro_f1': round(r['robust_macro_f1'], 6)}
                              for i, r in enumerate(by_robust)],
        'per_config': {r['code']: {
            'full_rank': next(i + 1 for i, x in enumerate(by_full) if x['code'] == r['code']),
            'robust_rank': next(i + 1 for i, x in enumerate(by_robust) if x['code'] == r['code']),
        } for r in rows},
        'rows': rows,
    }

    # ---- 3. 2×2 因子设计主效应 ----
    def cell(sampler, cw):
        v = [r for r in rows if r['sampler'] == sampler and r['class_weight'] == cw]
        return {'codes': [x['code'] for x in v],
                'robust_macro_f1': (round(sum(x['robust_macro_f1'] for x in v) / len(v), 6)
                                    if v else None)}

    s_on = [r['robust_macro_f1'] for r in rows if r['sampler']]
    s_off = [r['robust_macro_f1'] for r in rows if not r['sampler']]
    w_on = [r['robust_macro_f1'] for r in rows if r['class_weight']]
    w_off = [r['robust_macro_f1'] for r in rows if not r['class_weight']]
    out['factor_design'] = {
        'cells': {
            'sampler_on__weight_on': cell(True, True),
            'sampler_on__weight_off': cell(True, False),
            'sampler_off__weight_on': cell(False, True),
            'sampler_off__weight_off': cell(False, False),
        },
        'sampler_effect': {
            'enabled_mean': round(sum(s_on) / len(s_on), 6),
            'disabled_mean': round(sum(s_off) / len(s_off), 6),
            'delta': round(sum(s_on) / len(s_on) - sum(s_off) / len(s_off), 6),
        },
        'class_weight_effect': {
            'enabled_mean': round(sum(w_on) / len(w_on), 6),
            'disabled_mean': round(sum(w_off) / len(w_off), 6),
            'delta': round(sum(w_on) / len(w_on) - sum(w_off) / len(w_off), 6),
        },
    }

    # ---- 4. S1 优势来源拆解（相对 M1）----
    m1 = data['M1']['report']['test_metrics']
    for other in ('M2', 'C2', 'S1'):
        om = data[other]['report']['test_metrics']
        gains, losses = [], []
        for i in range(n_classes):
            d = om['per_class_f1'][i] - m1['per_class_f1'][i]
            if d > 0.01:
                gains.append({'class_index': i, 'support': support[i], 'delta_f1': round(d, 6)})
            elif d < -0.01:
                losses.append({'class_index': i, 'support': support[i], 'delta_f1': round(d, 6)})
        gains.sort(key=lambda x: -x['delta_f1'])
        losses.sort(key=lambda x: x['delta_f1'])
        net = sum(x['delta_f1'] for x in gains) + sum(x['delta_f1'] for x in losses)
        out['s1_advantage_decomposition'][other] = {
            'vs': 'M1',
            'gains': gains,
            'losses': losses,
            'gain_sum': round(sum(x['delta_f1'] for x in gains), 6),
            'loss_sum': round(sum(x['delta_f1'] for x in losses), 6),
            'net_delta_macro_f1': round(net / n_classes, 6),
            'largest_gain_from_tiny_class': (
                gains[0]['support'] <= TINY_THRESHOLD if gains else None),
        }

    # ---- 5. 单点敏感性：极小类判定翻转 ----
    for r in rows:
        f1 = r['per_class_f1']
        out['single_point_sensitivity'][r['code']] = {
            'macro_f1_current': round(r['full_macro_f1'], 6),
            'tiny_class_f1_values': [
                {'class_index': i, 'support': support[i], 'f1': round(f1[i], 6)}
                for i in tiny
            ],
            # 若 idx20（n=2）由当前值变为全对 / 全错
            'if_idx20_perfect': round(r['full_macro_f1']
                                      - f1[20] / n_classes + 1.0 / n_classes, 6),
            'if_idx20_all_wrong': round(r['full_macro_f1']
                                        - f1[20] / n_classes + 0.0 / n_classes, 6),
            'one_image_swing': round(1.0 / n_classes, 6),
        }

    # ---- 6. 尾部 / 头部对比 ----
    head = [i for i, n in enumerate(support) if n >= 100]
    tail = [i for i, n in enumerate(support) if n < 10]
    out['head_tail_comparison'] = {}
    for r in rows:
        f1 = r['per_class_f1']
        out['head_tail_comparison'][r['code']] = {
            'head_classes': len(head),
            'head_macro_f1': round(sum(f1[i] for i in head) / len(head), 6),
            'tail_classes': len(tail),
            'tail_macro_f1': round(sum(f1[i] for i in tail) / len(tail), 6),
            'tail_recall': round(sum(r['per_class_recall'][i] for i in tail) / len(tail), 6),
        }

    # ---- 7. 收敛性核验 ----
    out['convergence_check'] = {}
    for code, name in RUNS:
        rep = data[code]['report']
        cfg = data[code]['run_config']['config']
        hist = rep['history']
        vf = [e.get('val_macro_f1') for e in hist if e.get('val_macro_f1') is not None]
        out['convergence_check'][code] = {
            'epochs_cap': cfg['epochs'],
            'epochs_run': len(hist),
            'best_epoch': rep['best_epoch'],
            'early_stopped': len(hist) < cfg['epochs'],
            'last5_val_macro_f1': [round(x, 6) for x in vf[-5:]],
            'plateaued': (max(vf[-4:]) - min(vf[-4:]) < 0.005) if len(vf) >= 4 else None,
        }

    os.makedirs(REPORTS, exist_ok=True)
    sp = os.path.join(REPORTS, 'm2_analysis.json')
    with io.open(sp, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # ---- 控制台摘要 ----
    print('=' * 74)
    print('  M2 对照实验分析')
    print('=' * 74)
    print(f'  测试集 {total_imgs} 张 / {n_classes} 类')
    print(f'  极小类 (n<={TINY_THRESHOLD})：{len(tiny)} 类 / {tiny_imgs} 张 '
          f'({tiny_imgs/total_imgs:.2%})')
    print(f'  稳健口径 (n>={ROBUST_MIN})：{len(robust)} 类 / {robust_imgs} 张 '
          f'({robust_imgs/total_imgs:.2%})')
    print()
    print('  排名对比：')
    hdr = f'    {"代号":<5}{"全23类":>10}{"名次":>6}{"稳健14类":>12}{"名次":>6}{"变化":>8}'
    print(hdr)
    for r in rows:
        fr = out['rankings']['per_config'][r['code']]['full_rank']
        rr = out['rankings']['per_config'][r['code']]['robust_rank']
        delta = rr - fr
        arrow = f'↓{delta}' if delta > 0 else (f'↑{-delta}' if delta < 0 else '—')
        print(f'    {r["code"]:<5}{r["full_macro_f1"]:>10.4f}{fr:>6}'
              f'{r["robust_macro_f1"]:>12.4f}{rr:>6}{arrow:>8}')
    print()
    fd = out['factor_design']
    print(f'  采样器主效应 : {fd["sampler_effect"]["delta"]:+.4f}')
    print(f'  加权主效应   : {fd["class_weight_effect"]["delta"]:+.4f}')
    print()
    s1 = out['s1_advantage_decomposition']['S1']
    print(f'  S1 vs M1 净变化 {s1["net_delta_macro_f1"]:+.4f}，'
          f'其中最大提升来自 n={s1["gains"][0]["support"]} 的类 '
          f'(+{s1["gains"][0]["delta_f1"]:.3f})')
    sp2 = out['single_point_sensitivity']
    print(f'  单点波动幅度 : ±{sp2["M1"]["one_image_swing"]:.4f} / 类')
    print()
    print(f'  已写入 {sp}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
