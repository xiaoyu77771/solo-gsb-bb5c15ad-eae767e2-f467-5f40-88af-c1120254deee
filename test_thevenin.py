"""两节点端口戴维南等效冒烟测试（开发用，不打进镜像）。

运行：python3 test_thevenin.py
"""
import math
import sys

from app.solver import CircuitError
from app.thevenin import thevenin

failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  -> {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def codes(payload):
    try:
        thevenin(payload)
        return None, None, None
    except CircuitError as e:
        return [g["code"] for g in e.errors], e.to_dict().get("stage"), e.errors


DIVIDER_NET = {
    "ground": "0",
    "nodes": ["0", "1", "2"],
    "elements": [
        {"id": "V1", "type": "V", "node_p": "1", "node_n": "0", "value": 10},
        {"id": "R1", "type": "R", "node_p": "1", "node_n": "2", "value": 10},
        {"id": "R2", "type": "R", "node_p": "2", "node_n": "0", "value": 20},
    ],
}

# ---------- 1. 分压网络 2→0：Voc=20/3 V，Req=10∥20=20/3 Ω ----------
r = thevenin({**DIVIDER_NET, "port": {"node_p": "2", "node_n": "0"}})
check("返回 ok", r["ok"] is True)
check("端口方向回显", r["port"] == {"node_p": "2", "node_n": "0"}, str(r["port"]))
check("分压端口 Voc=20/3",
      math.isclose(r["open_circuit_voltage"], 20 / 3, abs_tol=1e-10),
      str(r["open_circuit_voltage"]))
check("分压端口 Req=20/3（10∥20）",
      math.isclose(r["equivalent_resistance"], 20 / 3, abs_tol=1e-10),
      str(r["equivalent_resistance"]))

# ---------- 2. 端口方向取反：Voc 变号、Req 不变 ----------
r2 = thevenin({**DIVIDER_NET, "port": {"node_p": "0", "node_n": "2"}})
check("反向端口 Voc=-20/3",
      math.isclose(r2["open_circuit_voltage"], -20 / 3, abs_tol=1e-10),
      str(r2["open_circuit_voltage"]))
check("反向端口 Req 仍为 20/3",
      math.isclose(r2["equivalent_resistance"], 20 / 3, abs_tol=1e-10),
      str(r2["equivalent_resistance"]))

# ---------- 3. 直接接在理想电压源两端：Req=0 ----------
r3 = thevenin({**DIVIDER_NET, "port": {"node_p": "1", "node_n": "0"}})
check("理想电压源端口 Voc=10",
      math.isclose(r3["open_circuit_voltage"], 10.0, abs_tol=1e-10),
      str(r3["open_circuit_voltage"]))
check("理想电压源端口 Req=0",
      r3["equivalent_resistance"] == 0.0, str(r3["equivalent_resistance"]))

# ---------- 4. 纯电阻 + 电流源：Voc=-10 V，Req=5 Ω（电流源置零开路） ----------
r4 = thevenin({
    "ground": "0",
    "nodes": ["0", "1"],
    "elements": [
        {"id": "I1", "type": "I", "node_p": "1", "node_n": "0", "value": 2},
        {"id": "R1", "type": "R", "node_p": "1", "node_n": "0", "value": 5},
    ],
    "port": {"node_p": "1", "node_n": "0"},
})
check("电流源网络 Voc=-10",
      math.isclose(r4["open_circuit_voltage"], -10.0, abs_tol=1e-10),
      str(r4["open_circuit_voltage"]))
check("电流源置零后 Req=5",
      math.isclose(r4["equivalent_resistance"], 5.0, abs_tol=1e-10),
      str(r4["equivalent_resistance"]))

# ---------- 5. 双支路含源网络：10V+10Ω 与 2A+10Ω 并联 ----------
# KCL@1: (V1-10)/10 + 2 = 0 → V1 = -10；Req = 10 Ω
r5 = thevenin({
    "ground": "0",
    "nodes": ["0", "1", "2"],
    "elements": [
        {"id": "V1", "type": "V", "node_p": "2", "node_n": "0", "value": 10},
        {"id": "R1", "type": "R", "node_p": "2", "node_n": "1", "value": 10},
        {"id": "I1", "type": "I", "node_p": "1", "node_n": "0", "value": 2},
    ],
    "port": {"node_p": "1", "node_n": "0"},
})
check("含源并联 Voc=-10",
      math.isclose(r5["open_circuit_voltage"], -10.0, abs_tol=1e-9),
      str(r5["open_circuit_voltage"]))
check("含源并联 Req=10",
      math.isclose(r5["equivalent_resistance"], 10.0, abs_tol=1e-9),
      str(r5["equivalent_resistance"]))

# ---------- 6. 桥 T 网络端口（均非接地节点） ----------
# V1=10V 经 R1=10 到 2；R2=20: 2→0；R3=30: 2→3；I1=0.2: 3→0
bridge = {
    "ground": "0",
    "nodes": ["0", "1", "2", "3"],
    "elements": [
        {"id": "V1", "type": "V", "node_p": "1", "node_n": "0", "value": 10},
        {"id": "R1", "type": "R", "node_p": "1", "node_n": "2", "value": 10},
        {"id": "R2", "type": "R", "node_p": "2", "node_n": "0", "value": 20},
        {"id": "R3", "type": "R", "node_p": "2", "node_n": "3", "value": 30},
        {"id": "I1", "type": "I", "node_p": "3", "node_n": "0", "value": 0.2},
    ],
}
r6 = thevenin({**bridge, "port": {"node_p": "3", "node_n": "2"}})
# 开路：V2=16/3, V3=-2/3（见 test_solver 手算），Voc=V3-V2=-6
check("桥端口 Voc=-6",
      math.isclose(r6["open_circuit_voltage"], -6.0, abs_tol=1e-9),
      str(r6["open_circuit_voltage"]))
# 无源：I1 开路后 3 只经 R3 与 2 相连，1A 全部流过 R3 → Req=30
# （R1∥R2 只决定节点 2 相对地的共模电位，不影响 3-2 端口压差）
check("桥端口 Req=30",
      math.isclose(r6["equivalent_resistance"], 30.0, abs_tol=1e-9),
      str(r6["equivalent_resistance"]))

# ---------- 7. 不修改原请求体（置零 / 测试电流只作用于副本） ----------
payload7 = {**DIVIDER_NET, "port": {"node_p": "2", "node_n": "0"}}
thevenin(payload7)
check("原网络元件未被置零 / 追加",
      [e["value"] for e in payload7["elements"]] == [10, 10, 20]
      and all(e["type"] != "I" for e in payload7["elements"]),
      str(payload7["elements"]))

# ---------- 8. 无接地：失败落在开路阶段 ----------
c, stage, _ = codes({
    "ground": "",
    "nodes": ["0", "1"],
    "elements": [
        {"id": "V1", "type": "V", "node_p": "1", "node_n": "0", "value": 10},
        {"id": "R1", "type": "R", "node_p": "1", "node_n": "0", "value": 10},
    ],
    "port": {"node_p": "1", "node_n": "0"},
})
check("无接地报 no_ground", c == ["no_ground"], str(c))
check("无接地阶段为 open_circuit", stage == "open_circuit", str(stage))

# ---------- 9. 浮置子网：阶段一即报 floating_subnet ----------
c, stage, _ = codes({
    "ground": "0",
    "nodes": ["0", "1", "2", "3"],
    "elements": [
        {"id": "V1", "type": "V", "node_p": "1", "node_n": "0", "value": 10},
        {"id": "R1", "type": "R", "node_p": "1", "node_n": "0", "value": 10},
        {"id": "V2", "type": "V", "node_p": "2", "node_n": "3", "value": 5},
        {"id": "R2", "type": "R", "node_p": "2", "node_n": "3", "value": 100},
    ],
    "port": {"node_p": "2", "node_n": "3"},
})
check("浮置子网报 floating_subnet", c == ["floating_subnet"], str(c))
check("浮置子网阶段为 open_circuit", stage == "open_circuit", str(stage))

# ---------- 10. 电压源冲突：阶段一报 voltage_conflict ----------
c, stage, _ = codes({
    "ground": "0",
    "nodes": ["0", "1"],
    "elements": [
        {"id": "V1", "type": "V", "node_p": "1", "node_n": "0", "value": 12},
        {"id": "V2", "type": "V", "node_p": "1", "node_n": "0", "value": 5},
    ],
    "port": {"node_p": "1", "node_n": "0"},
})
check("电压源冲突报 voltage_conflict", c == ["voltage_conflict"], str(c))
check("冲突阶段为 open_circuit", stage == "open_circuit", str(stage))

# ---------- 11. 等值并联电压源：结构检查不冲突，但原网络矩阵本身奇异 ----------
# 两条相同的 5V 电压源约束使系数矩阵亏秩（与右端无关），开路阶段即 singular；
# 此时不存在唯一的开路电压，不能给出伪 Voc
c, stage, errs = codes({
    "ground": "0",
    "nodes": ["0", "1"],
    "elements": [
        {"id": "V1", "type": "V", "node_p": "1", "node_n": "0", "value": 5},
        {"id": "V2", "type": "V", "node_p": "1", "node_n": "0", "value": 5},
    ],
    "port": {"node_p": "1", "node_n": "0"},
})
check("等值并联报 singular", c == ["singular"], str(c))
check("singular 落在开路阶段（不返回伪 Voc）",
      stage == "open_circuit", str(stage))

# ---------- 12. 端口参数校验（不带 stage） ----------
base = {**DIVIDER_NET}

c, stage, _ = codes({**base, "port": {"node_p": "2", "node_n": "2"}})
check("同端报 port_validation", c == ["port_validation"], str(c))
check("参数校验不带 stage", stage is None, str(stage))

c, _, _ = codes({**base, "port": {"node_p": "9", "node_n": "0"}})
check("p 不在节点表报 port_validation", c == ["port_validation"], str(c))

c, _, _ = codes({**base, "port": {"node_p": "2", "node_n": ""}})
check("n 为空报 port_validation", c == ["port_validation"], str(c))

c, _, _ = codes({**base})
check("缺少 port 段报 port_validation", c == ["port_validation"], str(c))

# ---------- 13. 网络本身非法（元件端点不在表）时阶段一透传 validation ----------
c, stage, _ = codes({
    "ground": "0",
    "nodes": ["0", "1"],
    "elements": [
        {"id": "R1", "type": "R", "node_p": "1", "node_n": "9", "value": 10},
    ],
    "port": {"node_p": "1", "node_n": "0"},
})
check("网络内部非法透传 validation", c == ["validation"], str(c))
check("网络校验错误阶段为 open_circuit", stage == "open_circuit", str(stage))

print()
if failures:
    print(f"{len(failures)} 个用例失败: {failures}")
    sys.exit(1)
print("全部用例通过 ✔")
