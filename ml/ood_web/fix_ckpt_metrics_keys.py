# -*- coding: utf-8 -*-
"""一次性修复：为 M1_ood_tuned/best.pt 的 metrics 补齐标准契约键。

基线 checkpoint（M1_main_224）的 metrics schema 为 {'accuracy': .., 'macro_f1': .., ...}，
probe_live_server.py 与前端按此读取。finetune_ood.py 曾误存为 val_acc/val_macro_f1。
本脚本补齐别名键并保留 OOD 扩展字段。
"""
import os
import sys

import torch

# 可移植：<ROOT>/ml/ood_web/xxx.py → 向上三级为仓库根
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, 'ml'))
from config import MODELS_DIR  # noqa: E402

P = os.path.join(MODELS_DIR, 'M1_ood_tuned', 'best.pt')
ck = torch.load(P, map_location='cpu')
m = ck.get('metrics')
assert isinstance(m, dict), f'unexpected metrics: {type(m)}'
print('before:', sorted(m.keys()))

m.setdefault('accuracy', m.get('val_acc'))
m.setdefault('macro_f1', m.get('val_macro_f1'))
ck['metrics'] = m
torch.save(ck, P)
print('after:', sorted(m.keys()))
print('accuracy =', m['accuracy'], '| macro_f1 =', m['macro_f1'])
