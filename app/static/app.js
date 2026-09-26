"use strict";

const tubesBody = document.getElementById("tubes-body");
const formError = document.getElementById("form-error");
const results = document.getElementById("results");

// ---------- 管数行管理 ----------

function addTube(conc = "", vol = "") {
  const tr = document.createElement("tr");

  const tdNo = document.createElement("td");
  tdNo.className = "tube-no";

  const tdConc = document.createElement("td");
  const concInput = document.createElement("input");
  concInput.type = "number";
  concInput.step = "any";
  concInput.min = "0";
  concInput.value = conc;
  concInput.className = "tube-conc";
  tdConc.appendChild(concInput);

  const tdVol = document.createElement("td");
  const volInput = document.createElement("input");
  volInput.type = "number";
  volInput.step = "any";
  volInput.min = "0";
  volInput.value = vol;
  volInput.className = "tube-vol";
  tdVol.appendChild(volInput);

  const tdDel = document.createElement("td");
  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "btn danger";
  delBtn.textContent = "删除";
  delBtn.addEventListener("click", () => {
    tr.remove();
    renumber();
  });
  tdDel.appendChild(delBtn);

  tr.append(tdNo, tdConc, tdVol, tdDel);
  tubesBody.appendChild(tr);
  renumber();
}

function renumber() {
  tubesBody.querySelectorAll(".tube-no").forEach((td, i) => {
    td.textContent = `管 ${i + 1}`;
  });
}

// ---------- 输入收集与校验 ----------

const NUM_RE = /^-?(\d+(\.\d+)?|\.\d+)([eE][+-]?\d+)?$/;

function readNumber(id, name, errors) {
  const raw = document.getElementById(id).value.trim();
  if (!NUM_RE.test(raw)) {
    errors.push(`${name} 缺失或不是有效数字`);
    return null;
  }
  return raw; // 以字符串提交，避免浮点误差
}

function collectPayload() {
  const errors = [];
  const payload = {
    stock_concentration: readNumber("stock-conc", "母液浓度", errors),
    loss_volume: readNumber("loss", "预留损耗", errors),
    pipette_min: readNumber("pipette-min", "移液下限", errors),
    concentration_unit: document.getElementById("conc-unit").value.trim(),
    volume_unit: document.getElementById("vol-unit").value.trim() || "µL",
    tubes: [],
  };

  const rows = tubesBody.querySelectorAll("tr");
  if (rows.length === 0) errors.push("至少需要 1 个稀释管");
  rows.forEach((tr, i) => {
    const conc = tr.querySelector(".tube-conc").value.trim();
    const vol = tr.querySelector(".tube-vol").value.trim();
    if (!NUM_RE.test(conc)) errors.push(`管 ${i + 1} 目标浓度缺失或无效`);
    if (!NUM_RE.test(vol)) errors.push(`管 ${i + 1} 保留体积缺失或无效`);
    payload.tubes.push({ target_concentration: conc, retained_volume: vol });
  });

  return { payload, errors };
}

// ---------- 结果渲染 ----------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function render(data) {
  const cu = data.concentration_unit || "";
  const vu = data.volume_unit || "";

  const banner = document.getElementById("summary-banner");
  banner.className = data.feasible ? "ok" : "bad";
  banner.textContent = data.feasible
    ? "✓ 方案可行：所有步骤的浓度次序与移液体积均满足要求"
    : "✗ 方案存在不可行步骤，请根据下方标红提示调整参数";

  document.getElementById("total-stock").textContent = `${data.total_stock} ${vu}`;
  document.getElementById("total-diluent").textContent = `${data.total_diluent} ${vu}`;

  const stepsBox = document.getElementById("steps");
  stepsBox.innerHTML = "";

  data.steps.forEach((s) => {
    const card = el("div", "step-card" + (s.feasible ? "" : " infeasible"));

    const title = el("h3");
    title.appendChild(
      document.createTextNode(`管 ${s.tube} · 目标浓度 ${s.target_concentration} ${cu}`)
    );
    title.appendChild(
      el("span", "badge " + (s.feasible ? "ok" : "bad"), s.feasible ? "可行" : "不可行")
    );
    card.appendChild(title);

    const lines = el("ul", "step-lines");
    const items = [
      ["① 取液", `从 ${s.source} 取 ${s.transfer_in} ${vu}`],
      ["② 加液", `加入稀释液 ${s.diluent_volume} ${vu}，混匀，得 ${s.prepare_volume} ${vu}`],
    ];
    if (Number(s.tube) < data.steps.length) {
      items.push(["③ 转出", `取 ${s.transfer_out} ${vu} 至管 ${s.tube + 1}`]);
    }
    items.push([
      "④ 余留",
      `管中余留 ${s.retained_volume} + ${s.loss_volume} ${vu}（保留 ${s.retained_volume}，预留损耗 ${s.loss_volume}）`,
    ]);
    items.forEach(([label, text]) => {
      const li = el("li");
      li.appendChild(el("span", "num", label + "："));
      li.appendChild(document.createTextNode(text));
      lines.appendChild(li);
    });
    card.appendChild(lines);

    if (!s.feasible) {
      const ul = el("ul", "issues");
      s.issues.forEach((msg) => ul.appendChild(el("li", null, msg)));
      card.appendChild(ul);
    }

    stepsBox.appendChild(card);
  });

  results.hidden = false;
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- 提交 ----------

async function calculate() {
  formError.hidden = true;
  const { payload, errors } = collectPayload();
  if (errors.length > 0) {
    formError.textContent = errors.join("；");
    formError.hidden = false;
    return;
  }

  try {
    const resp = await fetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      throw new Error(detail || `请求失败（${resp.status}）`);
    }
    render(data);
  } catch (err) {
    formError.textContent = `计算失败：${err.message}`;
    formError.hidden = false;
  }
}

// ---------- 初始化 ----------

document.getElementById("add-tube").addEventListener("click", () => addTube());
document.getElementById("calc").addEventListener("click", calculate);

// 默认示例：1000 → 100 → 10 → 1
addTube("100", "100");
addTube("10", "100");
addTube("1", "100");
