"""FastAPI 入口：提供串联稀释计算 API 并托管前端静态页面。"""
from __future__ import annotations

from decimal import Decimal, getcontext
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .calc import compute_plan

# Decimal 计算精度（有效位数），足够覆盖多管连除的累积误差
getcontext().prec = 50

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="串联稀释配液计算器", version="1.0.0")


class TubeIn(BaseModel):
    target_concentration: Decimal = Field(..., description="目标浓度")
    retained_volume: Decimal = Field(..., description="保留体积")


class CalcRequest(BaseModel):
    stock_concentration: Decimal = Field(..., description="母液浓度")
    loss_volume: Decimal = Field(Decimal("0"), description="每管预留损耗体积")
    pipette_min: Decimal = Field(Decimal("0"), description="移液下限")
    concentration_unit: str = Field("", description="浓度单位（仅展示）")
    volume_unit: str = Field("µL", description="体积单位（仅展示）")
    tubes: List[TubeIn]


def _check_number(value: Decimal, name: str, allow_zero: bool = False) -> None:
    if not value.is_finite():
        raise HTTPException(status_code=400, detail=f"{name}必须是有限数值")
    if allow_zero:
        if value < 0:
            raise HTTPException(status_code=400, detail=f"{name}不能为负数")
    elif value <= 0:
        raise HTTPException(status_code=400, detail=f"{name}必须大于 0")


@app.post("/api/calculate")
def calculate(req: CalcRequest) -> dict:
    _check_number(req.stock_concentration, "母液浓度")
    _check_number(req.loss_volume, "预留损耗", allow_zero=True)
    _check_number(req.pipette_min, "移液下限", allow_zero=True)
    if not 1 <= len(req.tubes) <= 50:
        raise HTTPException(status_code=400, detail="管数需在 1~50 之间")
    for idx, tube in enumerate(req.tubes, start=1):
        _check_number(tube.target_concentration, f"管 {idx} 目标浓度")
        _check_number(tube.retained_volume, f"管 {idx} 保留体积")

    plan = compute_plan(
        stock_concentration=req.stock_concentration,
        loss_volume=req.loss_volume,
        pipette_min=req.pipette_min,
        targets=[t.target_concentration for t in req.tubes],
        retained=[t.retained_volume for t in req.tubes],
    )
    result = plan.to_dict()
    result["concentration_unit"] = req.concentration_unit
    result["volume_unit"] = req.volume_unit
    return result


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
