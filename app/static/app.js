"use strict";

const tubesBody = document.getElementById("tubes-body");
const formError = document.getElementById("form-error");
const results = document.getElementById("results");
const reviewBody = document.getElementById("review-body");
const reviewError = document.getElementById("review-error");
const reviewBanner = document.getElementById("review-banner");

// 最近一次配液方案的请求参数与结果；修改方案参数后复核结果即失效
let lastPlanPayload = null;
let lastPlanData = null;

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
    clearReviewResults();
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

  buildReviewForm(data);
  results.hidden = false;
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------- 执行复核 ----------

function clearReviewResults() {
  // 修改方案参数（含增删管）后清除旧复核结果，保留已录入的实际值（重新计算后会重建表单）
  reviewBody.querySelectorAll(".actual-conc").forEach((node) => (node.textContent = ""));
  reviewBody.querySelectorAll(".deviation").forEach((node) => {
    node.textContent = "";
    node.classList.remove("bad-text", "ok-text");
  });
  reviewBody.querySelectorAll(".remaining-val").forEach((node) => {
    node.textContent = "";
    node.classList.remove("bad-text", "ok-text");
  });
  reviewBody.querySelectorAll(".remaining").forEach((node) => (node.title = ""));
  reviewBody.querySelectorAll(".status-cell").forEach((node) => (node.innerHTML = ""));
  reviewBanner.hidden = true;
  reviewBanner.textContent = "";
  reviewBanner.className = "banner";
  reviewError.hidden = true;
  reviewError.textContent = "";
}

function buildReviewForm(data) {
  const cu = data.concentration_unit || "";
  const vu = data.volume_unit || "";
  reviewBody.innerHTML = "";

  data.steps.forEach((s) => {
    const tr = document.createElement("tr");

    tr.appendChild(el("td", null, `管 ${s.tube}`));
    tr.appendChild(el("td", "target-conc", `${s.target_concentration} ${cu}`));

    const tdIn = document.createElement("td");
    const inInput = document.createElement("input");
    inInput.type = "number";
    inInput.step = "any";
    inInput.min = "0";
    inInput.className = "rv-in";
    inInput.value = s.transfer_in;
    inInput.title = `方案取入量 ${s.transfer_in} ${vu}`;
    tdIn.appendChild(inInput);
    tr.appendChild(tdIn);

    const tdDil = document.createElement("td");
    const dilInput = document.createElement("input");
    dilInput.type = "number";
    dilInput.step = "any";
    dilInput.min = "0";
    dilInput.className = "rv-dil";
    dilInput.value = s.diluent_volume;
    dilInput.title = `方案加液量 ${s.diluent_volume} ${vu}`;
    tdDil.appendChild(dilInput);
    tr.appendChild(tdDil);

    tr.appendChild(el("td", "actual-conc"));
    tr.appendChild(el("td", "deviation"));

    const tdRem = el("td", "remaining");
    tdRem.appendChild(el("span", "remaining-val"));
    tdRem.appendChild(el("span", "remaining-req", ` / ${s.retained_volume} ${vu}`));
    tr.appendChild(tdRem);

    const tdStatus = el("td", "status-cell");
    tr.appendChild(tdStatus);

    reviewBody.appendChild(tr);
  });

  clearReviewResults();
}

function renderReview(data) {
  const cu = data.concentration_unit || "";
  const vu = data.volume_unit || "";
  const rows = reviewBody.querySelectorAll("tr");

  data.steps.forEach((s, idx) => {
    const tr = rows[idx];
    if (!tr) return;

    const concCell = tr.querySelector(".actual-conc");
    concCell.textContent = `${s.actual_concentration} ${cu}`;

    const devCell = tr.querySelector(".deviation");
    devCell.textContent = s.relative_deviation;
    devCell.classList.toggle("bad-text", !s.concentration_ok);
    devCell.classList.toggle("ok-text", s.concentration_ok);
    devCell.title = `容差 ±${s.tolerance}`;

    const remCell = tr.querySelector(".remaining");
    remCell.querySelector(".remaining-val").textContent = s.remaining_volume;
    remCell.querySelector(".remaining-val").classList.toggle("bad-text", !s.remaining_ok);
    remCell.querySelector(".remaining-val").classList.toggle("ok-text", s.remaining_ok);
    remCell.title = `实配总量 ${s.actual_prepare_volume} ${vu}` +
      (s.tube < data.steps.length ? `，扣除下一管实际取液 ${s.transfer_out} ${vu}` : "（末管）");

    const statusCell = tr.querySelector(".status-cell");
    statusCell.innerHTML = "";
    statusCell.appendChild(
      el("span", "badge " + (s.passed ? "ok" : "bad"), s.passed ? "合格" : "异常")
    );
    if (!s.passed) {
      const ul = el("ul", "cell-issues");
      s.issues.forEach((msg) => ul.appendChild(el("li", null, msg)));
      statusCell.appendChild(ul);
    }
  });

  reviewBanner.hidden = false;
  reviewBanner.className = data.passed ? "ok" : "bad";
  reviewBanner.textContent = data.passed
    ? "✓ 复核通过：各管实际浓度均在容差内，且余量满足保留要求"
    : "✗ 复核未通过：请查看标红的浓度超差或余量不足的管";
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
    // 方案参数已重新提交，旧复核结果失效
    lastPlanPayload = payload;
    lastPlanData = data;
    render(data);
  } catch (err) {
    formError.textContent = `计算失败：${err.message}`;
    formError.hidden = false;
  }
}

async function runReview() {
  reviewError.hidden = true;
  if (!lastPlanPayload || !lastPlanData) {
    reviewError.textContent = "请先计算配液方案";
    reviewError.hidden = false;
    return;
  }

  const errors = [];
  const toleranceRaw = document.getElementById("tolerance").value.trim();
  if (!NUM_RE.test(toleranceRaw) || Number(toleranceRaw) < 0) {
    errors.push("目标浓度相对容差缺失或无效");
  }

  const rows = reviewBody.querySelectorAll("tr");
  if (rows.length !== lastPlanData.steps.length) {
    errors.push("管数已变化，请重新计算配液方案后再复核");
  }

  // 方案参数被改过（含管数增删或数值修改）时必须先重新计算，避免按旧方案复核
  const current = collectPayload();
  if (current.errors.length > 0 ||
      JSON.stringify(current.payload) !== JSON.stringify(lastPlanPayload)) {
    errors.push("方案参数已修改，请先重新计算配液方案再执行复核");
  }

  const tubes = [];
  lastPlanData.steps.forEach((s, idx) => {
    const tr = rows[idx];
    const inRaw = tr ? tr.querySelector(".rv-in").value.trim() : "";
    const dilRaw = tr ? tr.querySelector(".rv-dil").value.trim() : "";
    if (!NUM_RE.test(inRaw) || Number(inRaw) < 0) {
      errors.push(`管 ${idx + 1} 实际取入量缺失或无效`);
    }
    if (!NUM_RE.test(dilRaw) || Number(dilRaw) < 0) {
      errors.push(`管 ${idx + 1} 实际加稀释液量缺失或无效`);
    }
    tubes.push({
      target_concentration: lastPlanPayload.tubes[idx].target_concentration,
      retained_volume: lastPlanPayload.tubes[idx].retained_volume,
      actual_transfer_in: inRaw,
      actual_diluent: dilRaw,
    });
  });

  if (errors.length > 0) {
    reviewError.textContent = errors.join("；");
    reviewError.hidden = false;
    return;
  }

  const payload = {
    stock_concentration: lastPlanPayload.stock_concentration,
    concentration_unit: lastPlanPayload.concentration_unit,
    volume_unit: lastPlanPayload.volume_unit,
    tolerance: toleranceRaw,
    tubes,
  };

  try {
    const resp = await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      throw new Error(detail || `请求失败（${resp.status}）`);
    }
    renderReview(data);
  } catch (err) {
    reviewError.textContent = `复核失败：${err.message}`;
    reviewError.hidden = false;
  }
}

// ---------- 初始化 ----------

document.getElementById("add-tube").addEventListener("click", () => addTube());
document.getElementById("calc").addEventListener("click", calculate);
document.getElementById("review-btn").addEventListener("click", runReview);

// 修改方案参数后清除旧复核结果（管数增删在对应按钮处理中单独清除）
document.getElementById("input-card").addEventListener("input", clearReviewResults);

// 默认示例：1000 → 100 → 10 → 1
addTube("100", "100");
addTube("10", "100");
addTube("1", "100");
