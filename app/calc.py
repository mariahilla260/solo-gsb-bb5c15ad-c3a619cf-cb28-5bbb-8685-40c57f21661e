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


def fmt_percent(value: Decimal) -> str:
    """百分比格式：输入为小数（如 0.125），输出 "12.5%"。"""
    return fmt(value * 100) + "%"


def fmt_signed_percent(value: Decimal) -> str:
    """带正负号的百分比格式，正值加 "+" 前缀。"""
    text = fmt_percent(value)
    return ("+" + text) if value > 0 else text


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


@dataclass
class ReviewStep:
    tube: int                       # 管号（1 起）
    source: str                     # 取液来源：母液 / 管 i-1
    target_concentration: Decimal   # 本管目标浓度
    actual_transfer_in: Decimal     # 实际取入量
    actual_diluent: Decimal         # 实际加稀释液量
    actual_total: Decimal           # 实配总量 = 实际取入量 + 实际加稀释液量
    actual_concentration: Decimal   # 实算浓度（按上一级实算浓度回算）
    relative_deviation: Decimal     # 相对偏差 = (实算浓度 - 目标浓度) / 目标浓度
    next_transfer_in: Decimal       # 下一管实际取液量（末管为 0）
    remaining: Decimal              # 余量 = 实配总量 - 下一管实际取液量（末管即实配总量）
    retained_volume: Decimal        # 该管要求保留体积
    issues: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues


@dataclass
class Review:
    steps: List[ReviewStep]
    relative_tolerance: Decimal  # 统一的目标浓度相对容差（小数）

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.steps)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "relative_tolerance": fmt(self.relative_tolerance),
            "relative_tolerance_percent": fmt(self.relative_tolerance * 100),
            "steps": [
                {
                    "tube": s.tube,
                    "source": s.source,
                    "target_concentration": fmt(s.target_concentration),
                    "actual_concentration": fmt(s.actual_concentration),
                    "relative_deviation": fmt(s.relative_deviation),
                    "relative_deviation_percent": fmt_signed_percent(s.relative_deviation),
                    "actual_transfer_in": fmt(s.actual_transfer_in),
                    "actual_diluent": fmt(s.actual_diluent),
                    "actual_total": fmt(s.actual_total),
                    "next_transfer_in": fmt(s.next_transfer_in),
                    "remaining": fmt(s.remaining),
                    "retained_volume": fmt(s.retained_volume),
                    "passed": s.passed,
                    "issues": s.issues,
                }
                for s in self.steps
            ],
        }


def compute_review(
    stock_concentration: Decimal,
    relative_tolerance: Decimal,
    targets: List[Decimal],
    retained: List[Decimal],
    actual_transfer_in: List[Decimal],
    actual_diluent: List[Decimal],
) -> Review:
    """执行复核计算（全程 Decimal）。

    1. 按管序以母液浓度或上一管的实算浓度回算各管实际浓度：
       实算浓度 Cᵢ = Cᵢ₋₁ · 实际取入量 / (实际取入量 + 实际加稀释液量)；
    2. 相对偏差 = (实算浓度 - 目标浓度) / 目标浓度，绝对值超过统一容差判定浓度超差；
    3. 余量 = 实配总量 - 下一管实际取液量（末管余量即其实配总量），
       低于该管要求保留体积判定余量不足。
    """
    n = len(targets)
    steps: List[ReviewStep] = []
    prev_conc = stock_concentration  # 上一级实算浓度，第 1 管为母液浓度
    for i in range(1, n + 1):
        tin = actual_transfer_in[i - 1]
        diluent = actual_diluent[i - 1]
        total = tin + diluent
        concentration = prev_conc * tin / total
        deviation = (concentration - targets[i - 1]) / targets[i - 1]
        next_in = actual_transfer_in[i] if i < n else Decimal(0)
        remaining = total - next_in

        issues: List[str] = []
        if abs(deviation) > relative_tolerance:
            issues.append(
                f"浓度超差：相对偏差 {fmt_signed_percent(deviation)} "
                f"超出容差 ±{fmt_percent(relative_tolerance)}"
            )
        if remaining < retained[i - 1]:
            issues.append(
                f"余量 {fmt(remaining)} 低于该管要求保留体积 {fmt(retained[i - 1])}"
            )

        steps.append(
            ReviewStep(
                tube=i,
                source="母液" if i == 1 else f"管 {i - 1}",
                target_concentration=targets[i - 1],
                actual_transfer_in=tin,
                actual_diluent=diluent,
                actual_total=total,
                actual_concentration=concentration,
                relative_deviation=deviation,
                next_transfer_in=next_in,
                remaining=remaining,
                retained_volume=retained[i - 1],
                issues=issues,
            )
        )
        prev_conc = concentration

    return Review(steps=steps, relative_tolerance=relative_tolerance)
