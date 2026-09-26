"""串联稀释配液核心计算（全程使用 Decimal，未取整值参与可行性判断）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List

# 显示精度：4 位小数（仅用于展示，判断一律用原始值）
DISPLAY_QUANT = Decimal("0.0001")


def fmt(value: Decimal) -> str:
    """格式化数值用于展示：保留 4 位小数并去掉多余的 0。"""
    if value == 0:
        return "0"
    quantized = value.quantize(DISPLAY_QUANT)
    if quantized == 0:
        # 非零但小于显示精度，用科学计数法提示
        return f"{value:.2E}"
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def fmt_precise(value: Decimal) -> str:
    """不可行提示中使用的高精度格式（约 10 位有效数字），避免舍入后与下限相同造成误解。"""
    return f"{value:.10g}"


@dataclass
class Step:
    tube: int                      # 管号（1 起）
    source: str                    # 取液来源：母液 / 管 i-1
    target_concentration: Decimal  # 本管目标浓度
    prepare_volume: Decimal        # 本管需制备的总体积
    transfer_in: Decimal           # 从上一级取入的体积
    diluent_volume: Decimal        # 加入的稀释液体积
    transfer_out: Decimal          # 转出给下一管的体积（末管为 0）
    retained_volume: Decimal       # 保留体积
    loss_volume: Decimal           # 预留损耗
    issues: List[str] = field(default_factory=list)

    @property
    def feasible(self) -> bool:
        return not self.issues


@dataclass
class Plan:
    steps: List[Step]
    total_stock: Decimal    # 母液总消耗
    total_diluent: Decimal  # 稀释液总消耗

    @property
    def feasible(self) -> bool:
        return all(s.feasible for s in self.steps)

    def to_dict(self) -> dict:
        return {
            "feasible": self.feasible,
            "total_stock": fmt(self.total_stock),
            "total_diluent": fmt(self.total_diluent),
            "steps": [
                {
                    "tube": s.tube,
                    "source": s.source,
                    "target_concentration": fmt(s.target_concentration),
                    "prepare_volume": fmt(s.prepare_volume),
                    "transfer_in": fmt(s.transfer_in),
                    "diluent_volume": fmt(s.diluent_volume),
                    "transfer_out": fmt(s.transfer_out),
                    "retained_volume": fmt(s.retained_volume),
                    "loss_volume": fmt(s.loss_volume),
                    "feasible": s.feasible,
                    "issues": s.issues,
                }
                for s in self.steps
            ],
        }


def compute_plan(
    stock_concentration: Decimal,
    loss_volume: Decimal,
    pipette_min: Decimal,
    targets: List[Decimal],
    retained: List[Decimal],
) -> Plan:
    """串联稀释计算。

    1. 从末管向前回推每管需制备的总体积：本管保留 + 预留损耗 + 后管从本管取走的量；
    2. 再算每级从前管（或母液）的取液量与需补加的稀释液量；
    3. 可行性（浓度次序、取液/加液是否低于移液下限）均按未取整的 Decimal 值判断。
    """
    n = len(targets)
    # concentrations[0] 为母液浓度，concentrations[i] 为第 i 管目标浓度
    concentrations = [stock_concentration, *targets]

    # 第一步：自末管向前回推制备量（下标 1..n，0 不用）
    prepare = [Decimal(0)] * (n + 1)
    transfer_in = [Decimal(0)] * (n + 1)  # 进入第 i 管的取液量
    prepare[n] = retained[n - 1] + loss_volume
    for i in range(n, 0, -1):
        # 由 C前 * V取 = C本 * V制 得本管需要从上一级取入的体积
        transfer_in[i] = prepare[i] * concentrations[i] / concentrations[i - 1]
        if i > 1:
            # 前一管除自身保留与损耗外，还要多制备本管要取走的部分
            prepare[i - 1] = retained[i - 2] + loss_volume + transfer_in[i]

    # 第二步：逐管计算稀释液量并检查可行性
    steps: List[Step] = []
    total_diluent = Decimal(0)
    for i in range(1, n + 1):
        diluent = prepare[i] - transfer_in[i]
        total_diluent += diluent

        issues: List[str] = []
        prev_label = "母液" if i == 1 else f"管 {i - 1}"
        if concentrations[i] >= concentrations[i - 1]:
            issues.append(f"浓度次序错误：目标浓度未低于{prev_label}浓度")
        if transfer_in[i] < pipette_min:
            issues.append(
                f"取液量 {fmt_precise(transfer_in[i])} 低于移液下限 {fmt(pipette_min)}"
            )
        if diluent <= 0:
            issues.append("稀释液量不大于 0，无法配制")
        elif diluent < pipette_min:
            issues.append(
                f"加液量 {fmt_precise(diluent)} 低于移液下限 {fmt(pipette_min)}"
            )

        steps.append(
            Step(
                tube=i,
                source="母液" if i == 1 else f"管 {i - 1}",
                target_concentration=targets[i - 1],
                prepare_volume=prepare[i],
                transfer_in=transfer_in[i],
                diluent_volume=diluent,
                transfer_out=transfer_in[i + 1] if i < n else Decimal(0),
                retained_volume=retained[i - 1],
                loss_volume=loss_volume,
                issues=issues,
            )
        )

    return Plan(steps=steps, total_stock=transfer_in[1], total_diluent=total_diluent)
