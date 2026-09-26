# 串联稀释配液计算器

基于 **FastAPI + Decimal + 原生 JavaScript** 的串联稀释（梯度稀释）配液 Web 应用。

输入母液浓度、逐级递减的目标浓度、各管保留体积、预留损耗与移液下限后，应用会：

1. **从末管向前回推**每管需要制备的总体积（本管保留 + 预留损耗 + 后管从本管取走的量）；
2. 再逐级计算**从前管（或母液）的取液量**与**需补加的稀释液量**；
3. 展示逐管操作步骤与**母液总消耗**、稀释液总消耗；
4. 当**浓度次序错误**（未逐级递减）或**取液 / 加液量低于移液下限**时，将对应步骤标红为不可行——判断一律基于**未取整的 Decimal 原始值**，页面显示值仅为 4 位小数舍入结果。

计算出方案后，还可在结果下方进行**执行复核**：为每管录入实际取入量、实际加稀释液量，并设置统一的目标浓度相对容差，后端按管序以母液或上一管的**实算浓度**回算各管实际浓度，逐管核对**浓度是否超差**与**余量是否满足该管要求保留体积**，页面展示实际浓度、相对偏差、余量与逐管状态；修改方案参数后旧复核结果会自动清除。

## 一键启动（Docker）

```bash
docker compose up --build
```

启动后访问：**http://localhost:8000**

- 首次启动会自动完成依赖安装与初始化，无需数据库或其他服务。
- 停止：`docker compose down`。

## 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| 对外端口 | `8000` | 修改 `docker-compose.yml` 中 `ports`，如改为 `"8080:8000"` 后访问 http://localhost:8080 |
| 容器内端口 | `8000` | 与 Dockerfile 的 `EXPOSE` / uvicorn 启动端口一致，一般无需改动 |

应用本身无环境变量等额外配置；浓度单位、体积单位、移液下限等均在页面中填写。

## 本地开发（不使用 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

访问 http://localhost:8000 。

## 计算说明

设母液浓度为 `C₀`，第 `i` 管目标浓度为 `Cᵢ`（需满足 `C₀ > C₁ > … > Cₙ`），保留体积 `Rᵢ`，每管预留损耗 `L`：

- 末管制备量：`Pₙ = Rₙ + L`
- 第 `i` 管从上一级取液：`Tᵢ = Pᵢ · Cᵢ / Cᵢ₋₁`
- 前管制备量（计入后管取液）：`Pᵢ₋₁ = Rᵢ₋₁ + L + Tᵢ`
- 第 `i` 管加稀释液：`Dᵢ = Pᵢ − Tᵢ`
- 母液总消耗：`T₁`

可行性检查（均按未取整值判断）：

- 目标浓度必须严格逐级递减且低于母液浓度；
- 每级取液量 `Tᵢ` 不得低于移液下限；
- 每级加液量 `Dᵢ` 必须大于 0 且不得低于移液下限。

## 复核说明

设第 `i` 管实际取入量 `Tᵢ`、实际加稀释液量 `Dᵢ`，上一级实算浓度为 `Ĉᵢ₋₁`（第 1 管为母液浓度 `C₀`），统一相对容差为 `ε`（如 5%）：

- 实配总量：`Pᵢ = Tᵢ + Dᵢ`
- 实算浓度（按管序递推）：`Ĉᵢ = Ĉᵢ₋₁ · Tᵢ / Pᵢ`
- 相对偏差：`(Ĉᵢ − Cᵢ) / Cᵢ`，绝对值超过 `ε` 判定**浓度超差**
- 余量：`Pᵢ − Tᵢ₊₁`（末管余量即其实配总量 `Pₙ`），低于该管要求保留体积 `Rᵢ` 判定**余量不足**

复核全部使用 Decimal 计算；每管的两种不合格原因分别标明，所有管均通过则整体复核通过。

## API

`POST /api/calculate`，请求体（数值可传字符串以保证精度）：

```json
{
  "stock_concentration": "1000",
  "loss_volume": "10",
  "pipette_min": "2",
  "concentration_unit": "µM",
  "volume_unit": "µL",
  "tubes": [
    { "target_concentration": "100", "retained_volume": "100" },
    { "target_concentration": "10",  "retained_volume": "100" },
    { "target_concentration": "1",   "retained_volume": "100" }
  ]
}
```

响应包含 `feasible`（整体是否可行）、`total_stock`（母液总消耗）、`total_diluent` 及 `steps` 逐管明细（取液量、加液量、制备量、转出量、不可行原因等）。交互式接口文档见 http://localhost:8000/docs 。

### 执行复核

`POST /api/review`，请求体（数值可传字符串以保证精度）：

```json
{
  "stock_concentration": "1000",
  "relative_tolerance_percent": "5",
  "concentration_unit": "µM",
  "volume_unit": "µL",
  "tubes": [
    { "target_concentration": "100", "retained_volume": "100", "actual_transfer_in": "11", "actual_diluent": "99" },
    { "target_concentration": "10",  "retained_volume": "100", "actual_transfer_in": "11", "actual_diluent": "99" },
    { "target_concentration": "1",   "retained_volume": "100", "actual_transfer_in": "11", "actual_diluent": "99" }
  ]
}
```

- `relative_tolerance_percent`：统一的目标浓度相对容差（百分数，`"5"` 表示 ±5%）；
- 每管需提供 `target_concentration`、`retained_volume`（要求保留体积）、`actual_transfer_in`（实际取入量）与 `actual_diluent`（实际加稀释液量）；实际取入 / 加液量均须 ≥ 0 且两者之和 > 0。

响应包含 `passed`（整体是否通过）、`relative_tolerance_percent` 及 `steps` 逐管明细：

- `actual_concentration`：按管序以母液或上一管实算浓度回算的实际浓度；
- `relative_deviation` / `relative_deviation_percent`：相对偏差（小数 / 带符号百分数）；
- `actual_total`：实配总量（实际取入量 + 实际加稀释液量）；
- `remaining`：余量 = 实配总量 − 下一管实际取液量，末管余量即其实配总量；
- `passed` / `issues`：逐管状态与不合格原因（浓度超差、余量低于要求保留体积分别标明）。

调用示例：

```bash
curl -X POST http://localhost:8000/api/review \
  -H "Content-Type: application/json" \
  -d '{"stock_concentration":"1000","relative_tolerance_percent":"5","tubes":[{"target_concentration":"100","retained_volume":"100","actual_transfer_in":"11","actual_diluent":"99"}]}'
```

## 目录结构

```
app/
  main.py            # FastAPI 入口与 API
  calc.py            # Decimal 高精度计算核心
  static/            # 原生 JS 前端（index.html / app.js / style.css）
Dockerfile
docker-compose.yml
requirements.txt
```
