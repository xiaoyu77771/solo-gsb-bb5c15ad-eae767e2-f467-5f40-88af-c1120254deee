"""两节点端口戴维南等效：分两个阶段复用 :func:`solve`。

请求体与 ``/api/solve`` 的网络 JSON 完全一致，另带一个 ``port`` 段：

    {
      ...网络...,
      "port": {"node_p": "2", "node_n": "0"}
    }

计算分两步：

1. **开路电压阶段**（``open_circuit``）：直接求解原网络，
   端口开路电压 ``Voc = V(p) - V(n)``；
2. **等效电阻阶段**（``equivalent_resistance``）：在网络**深拷贝**上把
   独立电压源置零（仍保留为 0 V 电压源，即理想短路线，不改变导电连通性）、
   独立电流源置零（开路移除），再从 n 向 p 注入 1 A 测试电流，
   等效电阻 ``Req = V(p) - V(n)``。

任一步网络无唯一解（无接地 / 浮置子网 / 电压源冲突 / 奇异）时抛出
:class:`StageCircuitError`，其 ``to_dict()`` 额外携带 ``stage`` 字段，
错误分组原样透传 :func:`solve` 的结构化结果，绝不返回编造的等效值。

端口参数本身（缺失 / 为空 / 同端 / 节点不在表中）无法开算，
直接抛出 :class:`CircuitError`（``port_validation``），与扫描的
``sweep_validation`` 处理方式一致。
"""

from __future__ import annotations

import copy
from typing import Any

from .solver import CircuitError, solve

# 测试电流源的内部编号（与用户元件编号撞车时追加序号）
_TEST_SRC_ID = "__Itest__"
_TEST_CURRENT = 1.0
# 与 solver 内节点电压的零门槛保持一致
_ZERO_TOL = 1e-12


class StageCircuitError(CircuitError):
    """带阶段标记的电路错误：:attr:`stage` 标识失败发生在哪一步。"""

    def __init__(self, stage: str, errors: list[dict[str, Any]]):
        self.stage = stage
        super().__init__(errors)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["stage"] = self.stage
        return data


def _reject(items: list[dict[str, str]]) -> CircuitError:
    return CircuitError(
        [{"code": "port_validation", "message": "端口参数未通过校验", "items": items}]
    )


def _node_names(payload: dict[str, Any]) -> list[str]:
    """从请求体兜底提取去重后的节点名（与 sweep 的兜底推导同款）。"""
    raw_nodes = payload.get("nodes")
    names: list[str] = []
    if isinstance(raw_nodes, list):
        seen: set[str] = set()
        for raw in raw_nodes:
            name = str(raw).strip() if raw is not None else ""
            if name and name not in seen:
                seen.add(name)
                names.append(name)
    return names


def thevenin(payload: dict[str, Any]) -> dict[str, Any]:
    """计算两节点端口的戴维南等效参数，失败时抛出 :class:`CircuitError`。"""
    if not isinstance(payload, dict):
        raise _reject([{"ref": "-", "detail": "请求体应为对象"}])

    # ------------------------------------------------------------- 端口参数
    port = payload.get("port")
    if not isinstance(port, dict):
        raise _reject([{"ref": "-", "detail": "缺少 port 端口参数对象"}])

    problems: list[dict[str, str]] = []
    node_p = str(port.get("node_p") or "").strip()
    node_n = str(port.get("node_n") or "").strip()
    if not node_p:
        problems.append({"ref": "端口正端 p", "detail": "未选择端口正端 p 节点"})
    if not node_n:
        problems.append({"ref": "端口负端 n", "detail": "未选择端口负端 n 节点"})
    if node_p and node_n and node_p == node_n:
        problems.append(
            {"ref": "端口", "detail": f"端口两端不能为同一节点（当前均为“{node_p}”）"}
        )

    node_set = set(_node_names(payload))
    if node_p and node_p not in node_set:
        problems.append(
            {"ref": "端口正端 p", "detail": f"端口正端节点“{node_p}”不在节点表中"}
        )
    if node_n and node_n not in node_set:
        problems.append(
            {"ref": "端口负端 n", "detail": f"端口负端节点“{node_n}”不在节点表中"}
        )

    if problems:
        raise _reject(problems)

    # ------------------------------------------ 阶段一：原网络求开路端电压
    try:
        oc_result = solve(payload)
    except CircuitError as exc:
        raise StageCircuitError("open_circuit", exc.errors)

    oc_voltage = {row["id"]: float(row["voltage"]) for row in oc_result["node_voltages"]}
    v_open = oc_voltage[node_p] - oc_voltage[node_n]
    if abs(v_open) < _ZERO_TOL:
        v_open = 0.0

    # ------------------- 阶段二：独立源置零后注入 1A 测试电流求等效电阻
    passive = copy.deepcopy(payload)
    raw_elements = passive.get("elements")
    elements = raw_elements if isinstance(raw_elements, list) else []
    # 独立电流源置零 = 开路移除；独立电压源置零 = 0V（保留支路，即短路）
    kept: list[dict[str, Any]] = []
    for e in elements:
        if not isinstance(e, dict):
            kept.append(e)  # 交给 solve 做格式校验
            continue
        etype = str(e.get("type") or "").strip().upper()
        if etype == "I":
            continue
        if etype == "V":
            e["value"] = 0.0
        kept.append(e)

    existing_ids = {
        str(e.get("id") or "").strip() for e in kept if isinstance(e, dict)
    }
    test_id = _TEST_SRC_ID
    suffix = 0
    while test_id in existing_ids:
        suffix += 1
        test_id = f"{_TEST_SRC_ID}{suffix}"
    # 电流方向 n -> p：电流从 n 流出、注入 p，故无源网络上 V(p)-V(n) = Req·1A
    kept.append(
        {"id": test_id, "type": "I", "node_p": node_n, "node_n": node_p,
         "value": _TEST_CURRENT}
    )
    passive["elements"] = kept

    try:
        test_result = solve(passive)
    except CircuitError as exc:
        raise StageCircuitError("equivalent_resistance", exc.errors)

    test_voltage = {
        row["id"]: float(row["voltage"]) for row in test_result["node_voltages"]
    }
    r_eq = (test_voltage[node_p] - test_voltage[node_n]) / _TEST_CURRENT
    if abs(r_eq) < _ZERO_TOL:
        r_eq = 0.0

    # 两个阶段的数值稳定性警告合并去重（置零不改变系数矩阵，警告通常一致）
    warnings: list[str] = []
    for result in (oc_result, test_result):
        for w in result.get("warnings", []):
            if w not in warnings:
                warnings.append(w)

    return {
        "ok": True,
        "port": {"node_p": node_p, "node_n": node_n},
        "open_circuit_voltage": v_open,
        "equivalent_resistance": r_eq,
        "warnings": warnings,
    }
