# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 推理服务

职责：
  · 单例加载 ResNet18 权重（懒加载 + 线程安全）
  · 复用 ml/dataset/preprocess.py 的【唯一预处理入口】，保证与训练逐元素一致
  · 输出 Top-5 候选、置信度、推理耗时
  · 并发闸门（PRD 决策基线：单机最大并发推理 3）

PRD §10.4.2 硬要求：训练与推理两条流水线必须产出逐元素相同的张量，容差 0。
本模块【不自己写任何 resize/normalize 逻辑】，一律调用 preprocess_for_inference()。
"""

import os
import sys
import threading
import time
from typing import Any

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

ROOT = os.path.dirname(_BACKEND)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.core.config import settings       # noqa: E402
from app.core.errors import (              # noqa: E402
    BizError, E_42201, E_42202, E_50301, E_50302,
)

# 推理闸门：限制同时推理的请求数
_INFER_SEMAPHORE = threading.BoundedSemaphore(settings.max_concurrent_infer)


class ModelNotReady(RuntimeError):
    pass


class _Engine:
    """推理引擎单例。首次调用时才加载权重。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready = False
        self._model: Any = None
        self._torch: Any = None
        self._preprocess = None
        self._meta: dict[str, Any] = {}
        self._load_error: str | None = None

    # ---- 加载 ----

    def load(self, *, strict: bool = True) -> None:
        """加载模型。strict=True 时加载失败直接抛 50301。"""
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            try:
                self._do_load()
                self._ready = True
                self._load_error = None
            except Exception as e:
                self._load_error = f'{type(e).__name__}: {e}'
                if strict:
                    raise BizError(E_50301, f'识别服务暂不可用：模型加载失败（{self._load_error}）')

    def _do_load(self) -> None:
        import torch
        from torch import nn

        # 复用训练侧模型定义与预处理，避免结构/流程漂移
        sys.path.insert(0, os.path.join(ROOT, 'ml'))
        from dataset.preprocess import IMG_SIZE, preprocess_for_inference
        from dataset.species_meta import INDEX_TO_CN, INDEX_TO_SCI, NUM_CLASSES

        ckpt_path = settings.model_path
        if not os.path.exists(ckpt_path):
            raise FileNotFoundError(f'权重文件不存在: {ckpt_path}')

        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)

        # checkpoint 结构（见 ml/training/train.py）：
        #   {'state_dict': ..., 'config': ..., 'epoch': ..., 'metrics': ...,
        #    'species_index_to_cn': ..., 'species_index_to_sci': ...}
        if isinstance(ckpt, dict) and 'state_dict' in ckpt:
            state = ckpt['state_dict']
        elif isinstance(ckpt, dict) and 'model' in ckpt:
            state = ckpt['model']
        else:
            state = ckpt

        # 模型结构必须与训练侧 build_model() 完全一致：
        #   resnet18，且 m.fc 整体替换为 nn.Sequential(Dropout, Linear)
        #   注意【不是】在 resnet18 外套一层 Sequential —— 键名会变成 0.xxx
        from torchvision import models as tvm
        dropout = 0.3
        ncls = NUM_CLASSES
        if isinstance(ckpt, dict) and isinstance(ckpt.get('config'), dict):
            cfg = ckpt['config']
            dropout = float(cfg.get('dropout', dropout))
            ncls = int(cfg.get('num_classes', ncls))

        model = tvm.resnet18(weights=None)
        in_features = model.fc.in_features
        model.fc = nn.Sequential(nn.Dropout(p=dropout), nn.Linear(in_features, ncls))
        model.load_state_dict(state, strict=True)
        model.eval().to(device)

        self._torch = torch
        self._model = model
        self._preprocess = preprocess_for_inference

        # 类别名映射优先用 checkpoint 内嵌的，保证与训练侧同源；
        # 缺失时回退到 ml/dataset/species_meta.py
        i2cn = INDEX_TO_CN
        i2sci = INDEX_TO_SCI
        if isinstance(ckpt, dict):
            if ckpt.get('species_index_to_cn'):
                i2cn = {int(k): v for k, v in ckpt['species_index_to_cn'].items()}
            if ckpt.get('species_index_to_sci'):
                i2sci = {int(k): v for k, v in ckpt['species_index_to_sci'].items()}

        self._meta = {
            'device': device,
            'img_size': IMG_SIZE,
            'num_classes': ncls,
            'index_to_cn': i2cn,
            'index_to_sci': i2sci,
            'ckpt': ckpt_path,
            'model_version': _model_version(ckpt),
            'trained_epoch': ckpt.get('epoch') if isinstance(ckpt, dict) else None,
            'trained_metrics': ckpt.get('metrics') if isinstance(ckpt, dict) else None,
        }

    # ---- 状态 ----

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def describe(self, *, try_load: bool = True) -> dict:
        """状态描述。

        【为什么要 try_load】加载是懒加载（首次推理才读权重）。
        若 describe() 不尝试加载，/api/health 会永远报 ready=False，
        与实际能否推理不符 —— 这是最容易误导运维的假阴性。
        故默认尝试一次加载；失败不抛错，只记在 load_error 里。
        """
        if try_load and not self._ready:
            self.load(strict=False)
        d = {
            'ready': self._ready,
            'load_error': self._load_error,
            'ckpt': settings.model_path,
            'ckpt_exists': os.path.exists(settings.model_path),
            'num_classes': 23,
            'img_size': 224,
            'device': 'cpu',
        }
        if self._ready:
            d.update({
                'device': self._meta['device'],
                'model_version': self._meta['model_version'],
                'trained_epoch': self._meta.get('trained_epoch'),
                'trained_metrics': self._meta.get('trained_metrics'),
            })
        return d

    # ---- 推理 ----

    def predict(self, source, *, top_k: int = 5) -> dict:
        """对单张图像推理。

        source 支持 path / bytes / file-like / PIL.Image。

        返回：
          {
            class_index, cn_name, latin_name, confidence,   # Top-1
            candidates: [{rank, class_index, cn_name, latin_name, confidence}, ...],
            inference_ms, model_version, probabilities
          }

        命名对齐 D7：cn_name / latin_name（非 species_name / sci_name）。
        candidates 的字段顺序与 candidates_json 的写入结构一致。
        """
        if not self._ready:
            self.load(strict=False)
        if not self._ready:
            raise BizError(E_50301, f'识别服务暂不可用：模型未加载（{self._load_error}）')

        if not _INFER_SEMAPHORE.acquire(blocking=False):
            raise BizError(E_50302, f'请求队列已满（并发上限 {settings.max_concurrent_infer}）')

        try:
            t0 = time.perf_counter()
            torch = self._torch

            try:
                tensor = self._preprocess(source)          # (1,3,224,224) float32
            except Exception as e:
                raise _translate_image_error(e)

            model = self._model
            dev = self._meta['device']
            tensor = tensor.to(dev, non_blocking=True)

            with torch.inference_mode():
                logits = model(tensor)
                probs = torch.softmax(logits.float(), dim=1)[0]

            k = min(top_k, probs.numel())
            vals, idxs = torch.topk(probs, k)
            values = vals.detach().cpu().tolist()
            indices = idxs.detach().cpu().tolist()
            ms = int((time.perf_counter() - t0) * 1000)

            i2cn = self._meta['index_to_cn']
            i2sci = self._meta['index_to_sci']

            candidates = [
                {
                    'rank': r + 1,
                    'class_index': ci,
                    'cn_name': i2cn.get(ci, f'fish_{ci + 1}'),
                    'latin_name': i2sci.get(ci, ''),
                    'confidence': round(float(p), 6),
                }
                for r, (ci, p) in enumerate(zip(indices, values))
            ]
            best = candidates[0]
            return {
                'class_index': best['class_index'],
                'cn_name': best['cn_name'],
                'latin_name': best['latin_name'],
                'confidence': best['confidence'],
                'candidates': candidates,
                'inference_ms': ms,
                'model_version': self._meta['model_version'],
                'probabilities': [round(float(p), 8)
                                  for p in probs.detach().cpu().tolist()],
            }
        finally:
            _INFER_SEMAPHORE.release()


def _model_version(ckpt) -> str:
    if isinstance(ckpt, dict):
        for k in ('version', 'model_version', 'run_name'):
            if k in ckpt:
                return str(ckpt[k])
    # 用权重文件修改时间做版本标识
    try:
        return time.strftime('%Y%m%d', time.localtime(os.path.getmtime(settings.model_path)))
    except Exception:
        return 'unknown'


def _translate_image_error(e: Exception) -> BizError:
    """把图像解码类异常翻译成 PRD 定义的业务码。

    42201 图像无法解码 / 42202 图像分辨率过低
    """
    msg = str(e)
    low = msg.lower()
    if 'resolution' in low or 'too small' in low or '分辨率' in msg:
        return BizError(E_42202, f'图像分辨率过低：{msg}')
    return BizError(E_42201, f'图像无法解码：{msg}')


# 模块级单例
engine = _Engine()


def get_engine() -> _Engine:
    return engine


def warmup() -> dict:
    """应用启动时预热（失败不阻塞启动，仅记录状态）。"""
    engine.load(strict=False)
    return engine.describe()


if __name__ == '__main__':
    print('推理服务自检')
    print('-' * 66)
    d = warmup()
    for k, v in d.items():
        print(f'  {k:16s} {v}')
    if d['ready']:
        import glob
        # 用数据集里的真实图片试推理
        base = os.path.join(ROOT, 'fish_image23', 'fish_image')
        pics = []
        for c in ('fish_1', 'fish_21', 'fish_18'):
            g = glob.glob(os.path.join(base, c, '*.png'))[:1]
            pics.extend(g)
        print()
        for p in pics:
            r = engine.predict(p)
            expect = os.path.basename(os.path.dirname(p))
            hit = '✓' if expect == f'fish_{r["class_index"] + 1}' else '✗'
            print(f'  {hit} {expect:8s} → idx={r["class_index"]:2d} '
                  f'{r["cn_name"]:12s} conf={r["confidence"]:.4f} {r["inference_ms"]}ms')
            print('      Top5: ' + ', '.join(
                f'{c["cn_name"]}:{c["confidence"]:.3f}' for c in r['candidates']))
    else:
        print(f'  ! 模型未就绪：{engine.load_error}')
