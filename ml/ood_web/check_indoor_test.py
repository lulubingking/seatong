# -*- coding: utf-8 -*-
"""M1_ood_tuned 在原始同分布测试集上的复核（与 M1 的 0.9963/0.9678 同口径）。"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for p in (_ROOT, os.path.join(_ROOT, 'ml'), os.path.join(_ROOT, 'ml', 'dataset'),
          os.path.join(_ROOT, 'ml', 'training')):
    if p not in sys.path:
        sys.path.insert(0, p)

import torch                                               # noqa: E402
from torch.utils.data import DataLoader                    # noqa: E402

from fish_dataset import FishDataset, build_eval_transform, load_split  # noqa: E402
from config import pick_device, DATA_ROOT                  # noqa: E402
from train import confusion_matrix, metrics_from_cm        # noqa: E402
from dataset.preprocess import IMG_SIZE                    # noqa: E402


def main() -> None:
    device = pick_device()
    ckpt = torch.load(os.path.join(_ROOT, 'ml', 'models', 'M1_ood_tuned', 'best.pt'),
                      map_location=device, weights_only=False)
    from torchvision import models as tvm
    from torch import nn
    cfgd = ckpt['config']
    model = tvm.resnet18(weights=None)
    model.fc = nn.Sequential(nn.Dropout(p=float(cfgd.get('dropout', 0.3))),
                             nn.Linear(model.fc.in_features, 23))
    model.load_state_dict(ckpt['state_dict'], strict=True)
    model.eval().to(device)

    split = load_split()
    ds = FishDataset(split['test'], build_eval_transform(), data_root=DATA_ROOT)
    dl = DataLoader(ds, batch_size=64, shuffle=False, num_workers=4, pin_memory=True)
    preds, labels = [], []
    with torch.inference_mode():
        for xb, yb in dl:
            logits = model(xb.to(device))
            preds.append(logits.argmax(1).cpu().numpy())
            labels.append(yb.numpy())
    import numpy as np
    m = metrics_from_cm(confusion_matrix(np.concatenate(preds),
                                         np.concatenate(labels), 23))
    print('M1_ood_tuned 同分布测试集:',
          'acc', m['accuracy'], '| macroF1', m['macro_f1'],
          '| weightedF1', m['weighted_f1'])
    print('M1 基线           : acc 0.996342 | macroF1 0.967835')
    print('回退               : acc', round(0.996342 - m['accuracy'], 4),
          '| F1', round(0.967835 - m['macro_f1'], 4), '（门槛 ≤0.01）')
    out = {'test_acc': m['accuracy'], 'test_macro_f1': m['macro_f1'],
           'test_weighted_f1': m['weighted_f1'],
           'gate_pass': m['accuracy'] >= 0.986342 and m['macro_f1'] >= 0.957835}
    with open(os.path.join(_ROOT, 'ml', 'models', 'M1_ood_tuned',
                           'testset_check.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
