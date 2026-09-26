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


PCT_QUANT = Decimal("0.0001")


def fmt_pct(value: Decimal, signed: bool = False) -> str:
    """把相对值（小数）格式化为百分比字符串，如 0.05123 -> '5.123%'；signed 时正数补 '+'。"""
    pct = (value * Decimal(100)).quantize(PCT_QUANT)
    text = format(pct, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if signed and pct > 0:
        text = "+" + text
    return text + "%"


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
    tube: int                          # 管号（1 起）
    source: str                        # 取液来源：母液 / 管 i-1
    target_concentration: Decimal      # 本管目标浓度
    actual_transfer_in: Decimal        # 实际从上一级取入体积
    actual_diluent: Decimal            # 实际加入稀释液体积
    actual_prepare_volume: Decimal     # 实配总量 = 实际取入 + 实际加液
    actual_concentration: Decimal      # 实算浓度（按母液或上一管实算浓度回算）
    transfer_out: Decimal              # 下一管实际从本管取走的体积（末管为 0）
    remaining_volume: Decimal          # 余量 = 实配总量 - 下一管实际取液（末管等于实配总量）
    retained_volume: Decimal           # 本管要求保留体积
    relative_deviation: Decimal        # 相对偏差（小数，有符号）：(实算浓度 - 目标浓度) / 目标浓度
    tolerance: Decimal                 # 目标浓度相对容差（小数，如 0.05 表示 ±5%）
    concentration_ok: bool = True      # |相对偏差| <= 容差
    remaining_ok: bool = True          # 余量 >= 要求保留体积（实配总量还须 > 0 才能计算浓度）
    issues: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.issues


@dataclass
class Review:
    steps: List[ReviewStep]

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.steps)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "steps": [
                {
                    "tube": s.tube,
                    "source": s.source,
                    "target_concentration": fmt(s.target_concentration),
                    "actual_transfer_in": fmt(s.actual_transfer_in),
                    "actual_diluent": fmt(s.actual_diluent),
                    "actual_prepare_volume": fmt(s.actual_prepare_volume),
                    "actual_concentration": fmt(s.actual_concentration),
                    "transfer_out": fmt(s.transfer_out),
                    "remaining_volume": fmt(s.remaining_volume),
                    "retained_volume": fmt(s.retained_volume),
                    "relative_deviation": fmt_pct(s.relative_deviation, signed=True),
                    "relative_deviation_abs": fmt_pct(abs(s.relative_deviation)),
                    "tolerance": fmt_pct(s.tolerance),
                    "concentration_ok": s.concentration_ok,
                    "remaining_ok": s.remaining_ok,
                    "passed": s.passed,
                    "issues": s.issues,
                }
                for s in self.steps
            ],
        }


def compute_review(
    stock_concentration: Decimal,
    targets: List[Decimal],
    retained: List[Decimal],
    actual_transfer_in: List[Decimal],
    actual_diluent: List[Decimal],
    tolerance: Decimal,
) -> Review:
    """执行复核。

    1. 按管序逐管回算实际浓度：
       第 1 管以母液浓度为上一级浓度，第 i 管以第 i-1 管的实算浓度为上一级浓度，
       实算浓度 = 上一级浓度 × 实际取入量 / 实配总量（实配总量 = 实际取入 + 实际加液）；
    2. 逐管计算余量：实配总量扣除下一管实际取液量，末管余量等于其实配总量；
    3. 分别标出浓度超差（|相对偏差| > 容差）与余量低于要求保留体积的原因。
    """
    n = len(targets)
    steps: List[ReviewStep] = []
    prev_actual_conc = stock_concentration

    for i in range(1, n + 1):
        transfer_in_i = actual_transfer_in[i - 1]
        diluent_i = actual_diluent[i - 1]
        prepare_i = transfer_in_i + diluent_i
        transfer_out = actual_transfer_in[i] if i < n else Decimal(0)
        remaining = prepare_i - transfer_out

        issues: List[str] = []
        if prepare_i <= 0:
            # 取入量与加液量之和不大于 0，无法回算浓度
            actual_conc = Decimal(0)
            deviation = Decimal(0)
            concentration_ok = False
            issues.append("实配总量（实际取入 + 实际加稀释液）不大于 0，无法计算实际浓度")
        else:
            actual_conc = prev_actual_conc * transfer_in_i / prepare_i
            deviation = (actual_conc - targets[i - 1]) / targets[i - 1]
            concentration_ok = abs(deviation) <= tolerance
            if not concentration_ok:
                issues.append(
                    f"浓度超差：实际浓度 {fmt(actual_conc)} 相对目标浓度偏差 "
                    f"{fmt_pct(deviation, signed=True)}，超出容差 ±{fmt_pct(tolerance)}"
                )

        remaining_ok = remaining >= retained[i - 1]
        if not remaining_ok:
            if remaining < 0:
                issues.append(
                    f"余量不足：实配总量 {fmt(prepare_i)} 扣除下一管实际取液 "
                    f"{fmt(transfer_out)} 后为 {fmt(remaining)}，低于要求保留 "
                    f"{fmt(retained[i - 1])}"
                )
            else:
                issues.append(
                    f"余量 {fmt(remaining)} 低于该管要求保留体积 {fmt(retained[i - 1])}"
                )

        steps.append(
            ReviewStep(
                tube=i,
                source="母液" if i == 1 else f"管 {i - 1}",
                target_concentration=targets[i - 1],
                actual_transfer_in=transfer_in_i,
                actual_diluent=diluent_i,
                actual_prepare_volume=prepare_i,
                actual_concentration=actual_conc,
                transfer_out=transfer_out,
                remaining_volume=remaining,
                retained_volume=retained[i - 1],
                relative_deviation=deviation,
                tolerance=tolerance,
                concentration_ok=concentration_ok,
                remaining_ok=remaining_ok,
                issues=issues,
            )
        )
        # 下一管以本管实算浓度回算
        prev_actual_conc = actual_conc

    return Review(steps=steps)
