# -*- coding: utf-8 -*-
"""统一响应体与错误码（PRD §8.3.1 / §8.3.2）

响应体结构（PRD §8.3.1）：
    { "code": 0, "message": "ok", "data": {...}, "request_id": "..." }
    code = 0 表示成功；非 0 为业务错误码。

错误码分段（PRD §8.3.2 为唯一权威，本文件逐字对齐）：
    400xx 参数校验     401xx 认证与账号   403xx 权限
    404xx 资源不存在   409xx 冲突        413xx 体积
    415xx 类型         422xx 语义        429xx 限流
    500xx 服务端       503xx 不可用
"""

from typing import Any, Final

# ---------------- PRD §8.3.2 定义的 18 个错误码（不得增删改语义） ----------------

E_40001: Final[int] = 40001  # 请求参数缺失或格式错误
E_40101: Final[int] = 40101  # 未登录或令牌无效
E_40102: Final[int] = 40102  # 访问令牌已过期
E_40103: Final[int] = 40103  # 用户名或密码不正确
E_40104: Final[int] = 40104  # 账号已被禁用
E_40105: Final[int] = 40105  # 账号已锁定
E_40301: Final[int] = 40301  # 无权访问该资源
E_40401: Final[int] = 40401  # 资源不存在
E_40901: Final[int] = 40901  # 用户名已存在
E_41301: Final[int] = 41301  # 文件体积超过上限
E_41501: Final[int] = 41501  # 文件类型不支持
E_42201: Final[int] = 42201  # 图像无法解码
E_42202: Final[int] = 42202  # 图像分辨率过低
E_42901: Final[int] = 42901  # 游客试用额度已用尽
E_42902: Final[int] = 42902  # 请求过于频繁
E_50001: Final[int] = 50001  # 服务端内部错误
E_50301: Final[int] = 50301  # 识别服务暂不可用（模型未加载）
E_50302: Final[int] = 50302  # 请求队列已满

# ---------------- 前端层补充码（D9 §7.3 定义，非后端返回） ----------------
# NET-01 / CLI-01 / CLI-02 由前端本地产生，后端不返回，此处仅作登记注释。

# 业务码 → (HTTP 状态, 默认文案)
ERROR_TABLE: Final[dict[int, tuple[int, str]]] = {
    E_40001: (400, '请求参数缺失或格式错误'),
    E_40101: (401, '未登录或令牌无效'),
    E_40102: (401, '访问令牌已过期'),
    E_40103: (401, '用户名或密码不正确'),
    E_40104: (401, '账号已被禁用'),
    E_40105: (401, '账号已锁定'),
    E_40301: (403, '无权访问该资源'),
    E_40401: (404, '资源不存在'),
    E_40901: (409, '用户名已存在'),
    E_41301: (413, '文件体积超过上限'),
    E_41501: (415, '文件类型不支持'),
    E_42201: (422, '图像无法解码'),
    E_42202: (422, '图像分辨率过低'),
    E_42901: (429, '游客试用额度已用尽'),
    E_42902: (429, '请求过于频繁'),
    E_50001: (500, '服务端内部错误'),
    E_50301: (503, '识别服务暂不可用（模型未加载）'),
    E_50302: (503, '请求队列已满'),
}


class BizError(Exception):
    """业务异常。抛出后由全局处理器统一转成标准响应体。"""

    def __init__(self, code: int, message: str | None = None, *,
                 http_status: int | None = None, detail: Any = None):
        self.code = code
        self.message = message or ERROR_TABLE.get(code, (500, '未知错误'))[1]
        self.http_status = http_status or ERROR_TABLE.get(code, (500,))[0]
        self.detail = detail
        super().__init__(self.message)


def ok(data: Any = None, message: str = 'ok') -> dict:
    """成功响应体（不含 request_id，由中间件注入）。"""
    return {'code': 0, 'message': message, 'data': data}


def fail(code: int, message: str | None = None, detail: Any = None) -> dict:
    """失败响应体。"""
    return {
        'code': code,
        'message': message or ERROR_TABLE.get(code, (500, '未知错误'))[1],
        'data': detail,
    }


def http_status_of(code: int) -> int:
    return ERROR_TABLE.get(code, (500,))[0]


if __name__ == '__main__':
    print(f'PRD §8.3.2 定义错误码：{len(ERROR_TABLE)} 个（应为 18）')
    print()
    by_status: dict[int, list[int]] = {}
    for c, (s, _) in sorted(ERROR_TABLE.items()):
        by_status.setdefault(s, []).append(c)
    for s in sorted(by_status):
        codes = by_status[s]
        print(f'  HTTP {s:3d}  {len(codes)} 个: {codes}')
    print()
    # 校验：同一 HTTP 状态下承载多个业务码的情形（前端必须按业务码分支）
    multi = {s: c for s, c in by_status.items() if len(c) > 1}
    print(f'  一状态多码的情形: {len(multi)} 组')
    for s, c in sorted(multi.items()):
        print(f'    HTTP {s}: {c}')
