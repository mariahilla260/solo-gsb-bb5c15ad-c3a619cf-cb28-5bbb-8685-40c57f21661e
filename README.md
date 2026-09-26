# 串联稀释配液计算器

基于 **FastAPI + Decimal + 原生 JavaScript** 的串联稀释（梯度稀释）配液 Web 应用。

输入母液浓度、逐级递减的目标浓度、各管保留体积、预留损耗与移液下限后，应用会：

1. **从末管向前回推**每管需要制备的总体积（本管保留 + 预留损耗 + 后管从本管取走的量）；
2. 再逐级计算**从前管（或母液）的取液量**与**需补加的稀释液量**；
3. 展示逐管操作步骤与**母液总消耗**、稀释液总消耗；
4. 当**浓度次序错误**（未逐级递减）或**取液 / 加液量低于移液下限**时，将对应步骤标红为不可行——判断一律基于**未取整的 Decimal 原始值**，页面显示值仅为 4 位小数舍入结果。

## 执行复核

按方案实际操作后，可在方案结果**右侧的「执行复核」卡片**逐管录入**实际取入量**与**实际加稀释液量**，并设置统一的**目标浓度相对容差**（如 `0.05` 表示 ±5%，所有管共用）。点击「执行复核」后：

- 后端全程使用 **Decimal** 按管序回算各管实际浓度：第 1 管以母液浓度为上一级浓度，第 `i` 管以**第 `i-1` 管的实算浓度**为上一级浓度——
  `实际浓度ᵢ = 上一级实算浓度 × 实际取入量ᵢ / 实配总量ᵢ`，其中 `实配总量ᵢ = 实际取入量ᵢ + 实际加稀释液量ᵢ`；
- 逐管计算**余量**：`余量ᵢ = 实配总量ᵢ − 下一管实际取液量`（下一管的实际取液即其录入的实际取入量），**末管余量等于其实配总量**；
- 逐管标明原因：`|实际浓度 − 目标浓度| / 目标浓度 > 容差` 记为**浓度超差**；`余量 < 该管要求保留体积` 记为**余量不足**（余量为负时给出扣减明细）；
- 页面展示各管**实际浓度、相对偏差、余量（/ 要求保留）与逐管状态**，并给出整体复核结论。

**修改方案参数**（母液浓度、损耗、管数、各管目标浓度 / 保留体积等）后，已有的复核结果会立即清除；重新点击「计算配液方案」后按新方案重建复核录入表（实际录入框默认预填方案值）。

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

## API

### `POST /api/calculate` — 配液方案计算

请求体（数值可传字符串以保证精度）：

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

### `POST /api/review` — 执行复核

在 `/api/calculate` 得到方案、实际配液完成后调用。每管携带目标浓度、要求保留体积、**实际取入量**与**实际加稀释液量**，顶层携带统一的**目标浓度相对容差** `tolerance`（`0.05` 表示 ±5%；数值同样可传字符串以保证精度）：

```json
{
  "stock_concentration": "1000",
  "concentration_unit": "µM",
  "volume_unit": "µL",
  "tolerance": "0.05",
  "tubes": [
    { "target_concentration": "100", "retained_volume": "100", "actual_transfer_in": "12.21", "actual_diluent": "109.89" },
    { "target_concentration": "10",  "retained_volume": "100", "actual_transfer_in": "12.1",  "actual_diluent": "108.9" },
    { "target_concentration": "1",   "retained_volume": "100", "actual_transfer_in": "11",    "actual_diluent": "99" }
  ]
}
```

响应包含整体 `passed` 与逐管 `steps` 明细：

| 字段 | 说明 |
| --- | --- |
| `actual_concentration` | 以母液或上一管**实算浓度**按管序回算的实际浓度（Decimal 高精度，展示值 4 位小数） |
| `actual_prepare_volume` | 实配总量 = 实际取入量 + 实际加稀释液量 |
| `relative_deviation` | 实际浓度相对目标浓度的有符号偏差百分比字符串（如 `+8.9109%`）；另有 `relative_deviation_abs` |
| `tolerance` | 回显容差百分比（如 `5%`） |
| `concentration_ok` | `|相对偏差| ≤ 容差`（边界取等号，判为合格） |
| `transfer_out` | 下一管实际从本管取走的体积（末管为 `0`） |
| `remaining_volume` | 余量 = 实配总量 − 下一管实际取液；**末管余量 = 实配总量** |
| `retained_volume` | 该管要求保留体积 |
| `remaining_ok` / `passed` | 余量是否达标 / 该管是否整体合格（浓度与余量均合格） |
| `issues` | 逐管原因列表：浓度超差、余量低于要求保留体积（或余量为负）、实配总量不大于 0 等 |

校验规则与计算接口一致：各数值必须为有限数，实际取入 / 加液量允许为 0 但不能为负，管数需在 1~50 之间。前端在每次 `/api/calculate` 后以方案值预填复核录入框，因此也可直接把 `/api/calculate` 的方案值作为 `actual_*` 做"零偏差"自检。

## 目录结构

```
app/
  main.py            # FastAPI 入口与 API（/api/calculate 方案计算、/api/review 执行复核）
  calc.py            # Decimal 高精度计算核心（方案回推 + 复核回算）
  static/            # 原生 JS 前端（index.html / app.js / style.css）
Dockerfile
docker-compose.yml
requirements.txt
```
