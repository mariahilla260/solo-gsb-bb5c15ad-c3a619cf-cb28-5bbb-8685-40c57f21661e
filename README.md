# 串联稀释配液计算器

基于 **FastAPI + Decimal + 原生 JavaScript** 的串联稀释（梯度稀释）配液 Web 应用。

输入母液浓度、逐级递减的目标浓度、各管保留体积、预留损耗与移液下限后，应用会：

1. **从末管向前回推**每管需要制备的总体积（本管保留 + 预留损耗 + 后管从本管取走的量）；
2. 再逐级计算**从前管（或母液）的取液量**与**需补加的稀释液量**；
3. 展示逐管操作步骤与**母液总消耗**、稀释液总消耗；
4. 当**浓度次序错误**（未逐级递减）或**取液 / 加液量低于移液下限**时，将对应步骤标红为不可行——判断一律基于**未取整的 Decimal 原始值**，页面显示值仅为 4 位小数舍入结果。

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
