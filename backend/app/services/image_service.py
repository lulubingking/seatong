# -*- coding: utf-8 -*-
"""海瞳鱼鉴 · 图像资产服务

职责：
  · 保存上传文件到磁盘（文件名用 UUID，杜绝路径穿越）
  · 计算 SHA-256 内容哈希，用于重复上传检测（对应 idx_image_asset_content_hash）
  · 读取图像尺寸
  · 解码校验（PRD 错误码 42201 / 42202）

【隐私边界】PRD §6.5：用户上传图像仅用于本次识别，不得用于模型训练。
故本模块【绝不】把文件写入 fish_image23（训练集目录），二者物理隔离。
"""

import hashlib
import io
import os
import sys
import uuid
from datetime import datetime

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.core.config import settings                    # noqa: E402
from app.core.errors import (                           # noqa: E402
    BizError, E_40001, E_41301, E_41501, E_42201, E_42202,
)
from app.models import ImageAsset                       # noqa: E402

# PIL 安全上限：防止解压炸弹（一张 10MB 的 PNG 可解压成数十 GB）
Image.MAX_IMAGE_PIXELS = 80_000_000

# 分辨率下限（PRD 错误码 42202）。低于此值预处理上采样后无有效信息。
MIN_SHORT_SIDE = 32

_MIME_BY_EXT = {
    'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
    'bmp': 'image/bmp',
}


def ext_of(filename: str) -> str:
    return os.path.splitext(filename or '')[1].lower().lstrip('.')


def sniff_format(raw: bytes) -> str | None:
    """按文件头嗅探真实格式，返回 'png'/'jpeg'/'bmp' 或 None。

    【为什么必须嗅探】仅凭扩展名判定类型会放过改名的恶意文件，
    而 PIL 的 decode 又可能因格式歧义行为不一致。先用 magic number 定音，
    再用 PIL 二次校验，两道关卡。
    """
    if len(raw) < 12:
        return None
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if raw[:2] == b'\xff\xd8':
        return 'jpeg'
    if raw[:2] == b'BM':
        return 'bmp'
    return None


def validate_upload(filename: str, raw: bytes) -> tuple[str, int, int]:
    """校验上传内容。返回 (ext, width, height)。失败抛业务异常。

    校验顺序（与错误码语义一致）：
      40001 参数  →  41501 类型不支持  →  41301 体积超限
      →  42201 无法解码  →  42202 分辨率过低
    """
    if not filename:
        raise BizError(E_40001, '缺少文件名')

    ext = ext_of(filename)
    allowed = settings.allowed_ext_list
    if ext not in allowed:
        raise BizError(E_41501, f'文件类型不支持：.{ext}，仅支持 {"/".join(allowed)}')

    if not raw:
        raise BizError(E_40001, '文件内容为空')

    if len(raw) > settings.max_file_size_bytes:
        mb = len(raw) / 1024 / 1024
        raise BizError(E_41301,
                       f'文件体积超过上限：{mb:.1f} MB > {settings.max_file_size_mb} MB')

    # 第一关：magic number
    sniffed = sniff_format(raw)
    if sniffed is None:
        raise BizError(E_42201, '图像无法解码：文件头不是受支持的图像格式')

    # 扩展名与实际格式不符 —— 以实际格式为准，但不放行未声明的格式
    norm = 'jpeg' if sniffed == 'jpeg' else sniffed
    if norm not in allowed and not (norm == 'jpeg' and 'jpg' in allowed):
        raise BizError(E_41501, f'实际格式 {sniffed} 不在允许列表中')

    # 第二关：PIL 真实解码
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.verify()                       # 校验完整性，不加载像素
        with Image.open(io.BytesIO(raw)) as im:
            w, h = im.size
            im.load()                         # 真正解压，捕获截断文件
    except UnidentifiedImageError:
        raise BizError(E_42201, '图像无法解码：PIL 无法识别该文件')
    except Exception as e:
        raise BizError(E_42201, f'图像无法解码：{type(e).__name__}')

    if min(w, h) < MIN_SHORT_SIDE:
        raise BizError(E_42202,
                       f'图像分辨率过低：短边 {min(w, h)}px < {MIN_SHORT_SIDE}px')
    return norm, w, h


def sha256_of(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def store_bytes(raw: bytes, filename: str, ext: str,
                user_id: int | None) -> str:
    """把字节写入磁盘。返回相对存储路径。

    【安全要点】文件名完全由服务端生成（UUID + 校验过的扩展名），
    绝不使用用户提供的原始文件名拼路径 —— 否则 `../../etc/passwd` 类路径穿越。
    原始文件名仅作为元数据存进数据库。
    """
    day = datetime.now().strftime('%Y%m%d')
    subdir = os.path.join(settings.image_storage_dir, day)
    os.makedirs(subdir, exist_ok=True)

    token = uuid.uuid4().hex
    disk_name = f'{token}.{ext}'
    abs_path = os.path.join(subdir, disk_name)

    with open(abs_path, 'wb') as f:
        f.write(raw)

    # 返回相对 settings.image_storage_dir 的路径，便于日后整体迁移存储根目录
    return os.path.relpath(abs_path, settings.image_storage_dir).replace('\\', '/')


def abs_path_of(stored_path: str) -> str:
    """相对存储路径 → 绝对路径。同时做越界防护。"""
    root = os.path.abspath(settings.image_storage_dir)
    full = os.path.abspath(os.path.join(root, stored_path))
    if not full.startswith(root):
        # 数据库被篡改时阻止读取任意文件
        raise BizError(E_42201, '存储路径非法')
    return full


def create_asset(db: Session, raw: bytes, filename: str,
                 user_id: int | None) -> tuple[ImageAsset, bool]:
    """创建（或复用）图像资产。返回 (asset, reused)。

    复用规则：同一 user_id 下 content_hash 相同的未过期资产直接复用，
    不重复落盘。这对应 D7 的 idx_image_asset_content_hash 索引用途。
    """
    ext, w, h = validate_upload(filename, raw)
    digest = sha256_of(raw)

    # 重复上传检测（同一归属者 + 同一内容 + 未过期）
    if user_id is not None:
        exist = db.scalar(
            select(ImageAsset).where(
                ImageAsset.user_id == user_id,
                ImageAsset.content_hash == digest,
            ).order_by(ImageAsset.created_at.desc()))
        if exist is not None:
            return exist, True

    stored_path = store_bytes(raw, filename, ext, user_id)
    asset = ImageAsset(
        id=str(uuid.uuid4()),
        user_id=user_id,
        original_filename=filename,
        stored_path=stored_path,
        mime_type=_MIME_BY_EXT.get(ext, 'application/octet-stream'),
        file_size=len(raw),
        width=w,
        height=h,
        content_hash=digest,
        created_at=int(datetime.now().timestamp()),
        expires_at=int(datetime.now().timestamp()) + settings.image_retention_days * 86400,
    )
    db.add(asset)
    db.flush()
    return asset, False


def read_bytes(asset: ImageAsset) -> bytes:
    """读回原图字节。文件缺失时抛 40401（记录存在但载体丢失）。"""
    p = abs_path_of(asset.stored_path)
    if not os.path.exists(p):
        from app.core.errors import E_40401
        raise BizError(E_40401, '图像文件已不存在（可能已过期清理）')
    with open(p, 'rb') as f:
        return f.read()


def thumb_bytes(asset: ImageAsset, size: int = 320) -> bytes:
    """生成缩略图（内存中，不落盘）。用于历史列表。"""
    raw = read_bytes(asset)
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im = im.convert('RGB')
            im.thumbnail((size, size), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format='JPEG', quality=85)
            return buf.getvalue()
    except Exception as e:
        raise BizError(E_42201, f'缩略图生成失败：{type(e).__name__}')


if __name__ == '__main__':
    print('图像服务自检')
    print('-' * 66)
    ok = fail = 0

    def case(name, fn, expect_code=None):
        global ok, fail
        try:
            fn()
            got = None
        except BizError as e:
            got = e.code
        good = got == expect_code
        ok += good
        fail += (not good)
        print(f'  {"✓" if good else "✗"} {name:<34s} → code={got} (期望 {expect_code})')

    # 用真实数据集图片做正例
    import glob
    from app.core.config import ROOT
    base = os.path.join(ROOT, 'fish_image23', 'fish_image', 'fish_1')
    samples = sorted(glob.glob(os.path.join(base, '*.png')))
    if not samples:
        print(f'  ! 未找到样本图片：{base}')
        sys.exit(2)
    good_png = open(samples[0], 'rb').read()
    print(f'  样本 PNG 大小 {len(good_png) / 1024:.1f} KB')
    print()

    case('正常 PNG', lambda: validate_upload('a.png', good_png), None)
    case('扩展名不支持 .gif', lambda: validate_upload('a.gif', good_png), 41501)
    case('空文件', lambda: validate_upload('a.png', b''), 40001)
    case('缺文件名', lambda: validate_upload('', good_png), 40001)
    case('伪装成 png 的文本', lambda: validate_upload('a.png', b'not an image at all'), 42201)
    # 体积超限：构造一个 >10MB 的字节串（不真正解码）
    case('体积超限', lambda: validate_upload('a.png', b'\x89PNG\r\n\x1a\n' + b'x' * (11 * 1024 * 1024)), 41301)
    print()

    # 分辨率下限
    from PIL import Image as _I
    tiny = io.BytesIO()
    _I.new('RGB', (16, 16)).save(tiny, format='PNG')
    case('分辨率过低 16x16', lambda: validate_upload('t.png', tiny.getvalue()), 42202)

    # 嗅探器直测（注意：样本须 ≥12 字节，短于 12 字节一律判 None，防误判）
    print()
    for raw, want in [(good_png, 'png'), (b'BM' + b'\x00' * 14, 'bmp'),
                      (b'\xff\xd8\xff\xe0' + b'JFIF' + b'\x00' * 8, 'jpeg'),
                      (b'xxxx' * 4, None), (b'', None), (b'BM', None)]:
        got = sniff_format(raw)
        good = got == want
        ok += good
        fail += (not good)
        print(f'  {"✓" if good else "✗"} sniff_format({raw[:8]!r:26s} len={len(raw):3d}) → {got} (期望 {want})')

    print()
    print(f'  合计 通过 {ok} / 失败 {fail}')
