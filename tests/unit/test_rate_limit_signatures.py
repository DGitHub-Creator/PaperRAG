"""限流装饰器的形参形状门禁（结构性检查，不发请求）。

`@limiter.limit(...)` 在**进函数体之前**就要按名字取两个注入对象：

  - `request` 必须是 ASGI 的 `Request`——slowapi 用它算计数键；
  - `response` 必须是 `starlette.responses.Response`——本项目开了 `headers_enabled=True`，
    它要往这个对象上写 `X-RateLimit-*` 头。

任一对不上就抛 `Exception("parameter ... must be an instance of ...")`，而这个异常发生在端点内部，
Starlette 只能兜成 500。用"打一条请求看状态码"很容易测不出来，原因很阴：body 不合法时 FastAPI
在**校验阶段**就 422 返回，压根不执行 wrapper；所以拿 `json={}` 做断言的用例全绿，而真实
登录/对话（body 合法）全 500。本项目实测踩过两次——第一次 `request` 被叫成 `request_obj`，
修完才暴露 `response` 从来就没声明过。

所以这里不比行为，比形状：**凡被装饰过的路由，必须同时有 `request: Request` 与 `response: Response`**。
判据可证伪：把任一签名改回 `request_obj` 或删掉 `response` 都会红；一个被装饰端点都没扫到也红。
"""

from __future__ import annotations

import inspect

import pytest
from fastapi import Request, Response

pytestmark = pytest.mark.unit

# 两条都必须按这个名字与这个类型存在；缺哪条就报哪条
REQUIRED_PARAMS = (("request", Request), ("response", Response))


def _is_decorated(endpoint) -> bool:
    """`functools.wraps` 会留下 `__wrapped__`；裸函数没有。

    FastAPI 用同一个 `inspect.signature` 机制做注入，所以它看到的签名与这里看到的相同
    ——那正是缺陷能成立的前提：装饰器不改签名，签名里那个 `request` 就是请求体。
    """
    return getattr(endpoint, "__wrapped__", None) is not None


def _param_type_name(param: inspect.Parameter) -> str:
    ann = param.annotation
    if isinstance(ann, str):
        # 模块用 `from __future__ import annotations` 时注解是字符串
        return ann
    return getattr(ann, "__name__", str(ann))


def test_every_rate_limited_route_names_the_request_correctly():
    from backend.app import create_app

    offenders: list[str] = []
    checked = 0
    for route in create_app().routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or not _is_decorated(endpoint):
            continue
        checked += 1
        params = inspect.signature(endpoint).parameters
        path = getattr(route, "path", repr(endpoint))
        for name, expected in REQUIRED_PARAMS:
            param = params.get(name)
            if param is None:
                offenders.append(f"{path}：缺 `{name}: {expected.__name__}` 形参，限流 wrapper 会抛异常")
            elif _param_type_name(param) != expected.__name__:
                offenders.append(
                    f"{path}：`{name}` 形参类型是 {_param_type_name(param)}，应为 {expected.__name__}"
                )

    assert checked >= 5, f"只扫到 {checked} 个被限流装饰的端点，检查本身失效（历史基线是 5 条）"
    assert not offenders, "\n".join(offenders)
