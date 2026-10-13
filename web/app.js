import { bombOutRisk, chance } from "./predict.js";

const [payload, context] = await Promise.all(
  ["model.json", "context.json"].map(async (url) => (await fetch(url)).json()),
);

const STORAGE_KEY = "third-attempt:lifter";
const LABELS = ["Opener", "Second attempt", "Third attempt"];
const TITLES = ["Pick your opener", "Pick your second attempt", "Pick your third attempt"];
const MAXIMIN_BAND = context.maximin_band; // paper: best worst-case expected gain
const MAX_ROWS = 48;
const MAX_JUMP = 1.12;
const RARE_SHARE = 0.02; // fewer than 2% of lifters choose a jump in this 1% band
const BOMB_RATE = { Squat: 0.02, Bench: 0.026, Deadlift: 0.007 }; // results/descriptive.json

// IPF calibrated plates: [kg, colour, height px, thickness px]
const PLATES = [
  [25, "var(--plate-red)", 200, 30],
  [20, "var(--plate-blue)", 200, 25],
  [15, "var(--plate-yellow)", 178, 22],
  [10, "var(--plate-green)", 146, 20],
  [5, "var(--plate-white)", 104, 18],
  [2.5, "var(--plate-black)", 86, 14],
  [1.25, "var(--plate-chrome)", 72, 11],
  [0.5, "var(--plate-white)", 56, 8],
  [0.25, "var(--plate-chrome)", 46, 6],
];
const BAR_AND_COLLARS = 25;
const EXAMPLE_BEST = 180;

const state = {
  lifter: {
    lift: "Squat", best: null, sex: "M", equip: "Raw", priorMeets: 2, age: null,
    federation: "", tested: false, singleLift: false,
  },
  attempts: [null, null, null], // { w, made }
  step: 2.5,
  selected: null,
  custom: false,
  example: false, // first visit: show a sample lifter until the user enters their own best
};

const $ = (id) => document.getElementById(id);
const form = $("lifter-form");

// ---------- helpers ----------

const round2 = (x) => Math.round(x * 100) / 100;
const floorTo = (x, s) => round2(Math.floor(x / s + 1e-9) * s);
const ceilTo = (x, s) => round2(Math.ceil(x / s - 1e-9) * s);
const roundTo = (x, s) => round2(Math.round(x / s) * s);
const pct = (p, digits = 0) => `${(100 * p).toFixed(digits)}%`;

function fmtKg(w) {
  if (w == null || Number.isNaN(w)) return "—";
  return Number.isInteger(w) ? String(w) : String(round2(w));
}

function nextIndex() {
  const i = state.attempts.findIndex((a) => a === null);
  return i === -1 ? 3 : i;
}

function bestMadeSoFar(n) {
  return Math.max(0, ...state.attempts.slice(0, n).filter((a) => a && a.made).map((a) => a.w));
}

function base() {
  const l = state.lifter;
  return {
    female: l.sex === "F", equip: l.equip, tested: l.tested, singleLift: l.singleLift,
    priorMeets: l.priorMeets, age: l.age, federation: l.federation,
  };
}

function situation(w, n) {
  const { best } = state.lifter;
  const [a1, a2] = state.attempts;
  const s = { ...base(), attempt: n + 1, pct: best ? (100 * w) / best : null };
  if (n >= 1) {
    const prev = state.attempts[n - 1];
    s.jump = (100 * (w - prev.w)) / prev.w;
    s.prevMiss = !prev.made;
  }
  if (n === 2) {
    s.a1Miss = !a1.made;
    s.j12 = (100 * (a2.w - a1.w)) / a1.w;
  }
  return s;
}

/** Chance that nothing is made from attempt n onward when taking w now and repeating it after each miss. */
function bombFrom(w, n) {
  const lift = state.lifter.lift;
  if (n === 0) return bombOutRisk(payload, lift, situation(w, 0));
  const miss = 1 - chance(payload, lift, situation(w, n));
  if (n === 2) return miss;
  const a1 = state.attempts[0];
  const third = {
    ...base(), attempt: 3, pct: situation(w, 1).pct, jump: 0, prevMiss: true,
    a1Miss: !a1.made, j12: (100 * (w - a1.w)) / a1.w,
  };
  return miss * (1 - chance(payload, lift, third));
}

function evaluate(w, n) {
  const p = chance(payload, state.lifter.lift, situation(w, n));
  const out = { w, p };
  if (bestMadeSoFar(n) === 0) out.bomb = bombFrom(w, n);
  if (n >= 1) {
    const prev = state.attempts[n - 1];
    out.jump = (100 * (w - prev.w)) / prev.w;
    out.maximin = n === 2 && prev.made && out.jump >= MAXIMIN_BAND[0] && out.jump <= MAXIMIN_BAND[1];
    if (prev.made) {
      const shares = context.jump_shares[`${state.lifter.lift}_${n + 1}`];
      out.share = shares[Math.min(shares.length - 1, Math.max(0, Math.floor(out.jump)))];
      out.rare = out.share < RARE_SHARE;
    }
  }
  return out;
}

function candidateWeights(n) {
  const { best } = state.lifter;
  const s = state.step;
  let lo;
  let hi;
  if (n === 0) {
    if (!best) return [];
    lo = ceilTo(best * 0.8, s);
    hi = floorTo(best * 1.06, s);
  } else {
    const prev = state.attempts[n - 1];
    lo = prev.made ? round2(prev.w + s) : prev.w;
    hi = Math.max(lo, floorTo(prev.w * MAX_JUMP, s));
  }
  const all = [];
  for (let w = lo; w <= hi + 1e-9; w = round2(w + s)) all.push(w);
  const every = Math.ceil(all.length / MAX_ROWS);
  return all.filter((_, i) => i % every === 0);
}

function defaultWeight(n) {
  const { best } = state.lifter;
  const s = state.step;
  if (n === 0) return best ? floorTo(best * 0.91, s) : null;
  const prev = state.attempts[n - 1];
  if (!prev.made) return prev.w;
  return Math.max(round2(prev.w + s), roundTo(prev.w * (n === 1 ? 1.05 : 1.04), s));
}

// ---------- rendering ----------

function renderAttempts(n) {
  const list = $("attempts");
  list.innerHTML = "";
  state.attempts.forEach((a, i) => {
    const li = document.createElement("li");
    li.className = "attempt";
    const no = `<span class="attempt-no">${i + 1}</span>`;
    if (a) {
      const isLast = i === n - 1;
      li.innerHTML = `${no}
        <div class="attempt-body">
          <p class="attempt-label">${LABELS[i]}</p>
          <p class="attempt-weight">${fmtKg(a.w)} kg</p>
        </div>
        <div class="attempt-actions">
          <span class="result-lights ${a.made ? "good" : "no"}" role="img" aria-label="${a.made ? "Good lift" : "No lift"}"><i></i><i></i><i></i></span>
          ${isLast ? `<button class="link-btn" data-undo="${i}" type="button">Undo</button>` : ""}
        </div>`;
    } else if (i === n) {
      li.classList.add("is-next");
      li.innerHTML = `${no}
        <div class="attempt-body">
          <p class="attempt-label">${LABELS[i]} · up next</p>
          <span class="unit-input"><input class="attempt-input" type="number" inputmode="decimal" min="20" max="600" step="0.5"
            aria-label="${LABELS[i]} weight in kg" value="${state.selected ?? ""}"><span>kg</span></span>
        </div>
        <div class="attempt-actions">
          <button class="judge good" type="button" data-result="good" ${state.selected ? "" : "disabled"}><span class="dot"></span>Good</button>
          <button class="judge no" type="button" data-result="no" ${state.selected ? "" : "disabled"}><span class="dot"></span>No lift</button>
        </div>`;
    } else {
      li.classList.add("is-later");
      li.innerHTML = `${no}<div class="attempt-body"><p class="attempt-label">${LABELS[i]}</p><p class="attempt-weight">—</p></div>`;
    }
    list.append(li);
  });
}

function renderOptions(n) {
  const box = $("options");
  $("options-title").textContent = n < 3 ? TITLES[n] : "Meet done";
  if (n === 3) {
    box.innerHTML = `<p class="empty">All three attempts are in. Undo the last one to plan it again.</p>`;
    return;
  }
  const weights = candidateWeights(n);
  if (!weights.length) {
    box.innerHTML = `<p class="empty">Add your previous competition best under “You” to compare openers by weight, or type an opener into attempt 1.</p>`;
    return;
  }
  const rows = weights.map((w) => evaluate(w, n));
  const lastCol = rows[0].bomb != null ? "Bomb-out" : "Lifters who jump this much";
  const head = `<div class="option-head" aria-hidden="true"><span>Weight</span><span>${n === 0 ? "% best" : "Jump"}</span><span></span><span>Made</span><span>${lastCol}</span></div>`;
  box.innerHTML = head + rows.map((r) => {
    const meta = n === 0 ? `${((100 * r.w) / state.lifter.best).toFixed(0)}%` : `${r.jump >= 0 ? "+" : ""}${r.jump.toFixed(1)}%`;
    const extra = r.bomb != null ? `${pct(r.bomb, 1)} risk` : r.share != null ? `${r.share < 0.01 ? "<1" : Math.round(100 * r.share)}%${r.rare ? " · rare" : ""}` : "";
    const tag = r.maximin ? `<span class="tag">best worst case</span>` : "";
    return `<button type="button" class="option" role="option" data-w="${r.w}" aria-selected="${r.w === state.selected}">
      <span class="opt-weight">${fmtKg(r.w)}<small>kg</small></span>
      <span class="opt-meta">${meta}</span>
      <span class="bar" aria-hidden="true"><span style="width:${(100 * r.p).toFixed(1)}%"></span></span>
      <span class="opt-odds">${pct(r.p)}</span>
      <span class="opt-extra">${extra}${tag ? `<br>${tag}` : ""}</span>
    </button>`;
  }).join("");
}

function plateSet(w) {
  let side = (w - BAR_AND_COLLARS) / 2;
  const out = [];
  for (const plate of PLATES) {
    while (side + 1e-9 >= plate[0]) {
      out.push(plate);
      side = round2(side - plate[0]);
    }
  }
  return out;
}

let drawnWeight;
function renderBarbell(w) {
  if (w === drawnWeight) return;
  drawnWeight = w;
  const svg = $("barbell");
  const cy = 110;
  const inner = { left: 300, right: 700 };
  const sleeve = 250;
  const plates = w && w > BAR_AND_COLLARS ? plateSet(w) : [];
  const width = plates.reduce((sum, p) => sum + p[3] + 2, 0) + 18;
  const k = Math.min(1, (sleeve - 12) / Math.max(width, 1));
  let parts = `
    <rect x="${inner.left}" y="${cy - 5}" width="${inner.right - inner.left}" height="10" rx="2" fill="#8d959c"/>
    <rect x="${inner.left - sleeve}" y="${cy - 10}" width="${sleeve}" height="20" rx="3" fill="#b9c0c6"/>
    <rect x="${inner.right}" y="${cy - 10}" width="${sleeve}" height="20" rx="3" fill="#b9c0c6"/>
    <rect x="${inner.left - 12}" y="${cy - 24}" width="12" height="48" rx="2" fill="#9aa2a9"/>
    <rect x="${inner.right}" y="${cy - 24}" width="12" height="48" rx="2" fill="#9aa2a9"/>`;
  let offset = 14;
  plates.forEach(([, color, h, t], i) => {
    const tw = t * k;
    const delay = `animation-delay:${i * 45}ms`;
    const stroke = color.includes("white") ? ` stroke="#c7ccd0" stroke-width="1"`
      : color.includes("black") ? ` stroke="#5d646b" stroke-width="1.5"` : "";
    parts += `<rect class="plate" style="${delay}" x="${inner.right + offset}" y="${cy - h / 2}" width="${tw}" height="${h}" rx="4" fill="${color}"${stroke}/>`;
    parts += `<rect class="plate left" style="${delay}" x="${inner.left - offset - tw}" y="${cy - h / 2}" width="${tw}" height="${h}" rx="4" fill="${color}"${stroke}/>`;
    offset += tw + 2 * k;
  });
  if (plates.length) {
    parts += `<rect class="plate" style="animation-delay:${plates.length * 45}ms" x="${inner.right + offset}" y="${cy - 20}" width="14" height="40" rx="3" fill="#d5dade"/>`;
    parts += `<rect class="plate left" style="animation-delay:${plates.length * 45}ms" x="${inner.left - offset - 14}" y="${cy - 20}" width="14" height="40" rx="3" fill="#d5dade"/>`;
  }
  svg.innerHTML = parts;
  svg.setAttribute("aria-label", w ? `Barbell loaded to ${fmtKg(w)} kg` : "Empty barbell");
}

function renderPlatform(n) {
  const w = state.selected;
  $("platform-label").textContent = n < 3 ? LABELS[n] : "Best lift today";
  if (n === 3) {
    const best = bestMadeSoFar(3);
    $("platform-weight").textContent = best ? fmtKg(best) : "—";
    $("platform-odds").textContent = `${state.attempts.filter((a) => a.made).length}/3`;
    $("platform-note").innerHTML = best ? `Three attempts done. <strong>${fmtKg(best)} kg</strong> goes on your total.` : `Three red lights today. It happens: ${pct(BOMB_RATE[state.lifter.lift], 1)} of ${state.lifter.lift.toLowerCase()} entries end this way.`;
    renderBarbell(best || null);
    return;
  }
  $("platform-weight").textContent = fmtKg(w);
  $("platform-weight").parentElement.classList.toggle("is-empty", !w);
  $("platform-odds").classList.toggle("is-empty", !w);
  if (!w) {
    $("platform-odds").textContent = "—";
    $("platform-note").textContent = n === 0 ? "Enter your previous competition best, or type an opener, to see your odds." : "Pick a weight.";
    renderBarbell(null);
    return;
  }
  const prev = n > 0 ? state.attempts[n - 1] : null;
  if (prev && w < prev.w) {
    $("platform-odds").textContent = "—";
    $("platform-note").textContent = `Attempts can't go below your last one (${fmtKg(prev.w)} kg).`;
    renderBarbell(w);
    return;
  }
  const r = evaluate(w, n);
  $("platform-odds").textContent = pct(r.p);
  const per100 = Math.round(100 * r.p);
  let note;
  if (n === 0) {
    note = state.lifter.best
      ? `<strong>${per100} of every 100</strong> lifters in your spot made an opener at ${((100 * w) / state.lifter.best).toFixed(0)}% of their best.`
      : `<strong>${per100} of every 100</strong> lifters in your spot made their opener. Add your previous best for odds by weight.`;
    note += ` Opening here and repeating after a miss, <strong>${pct(r.bomb, 1)}</strong> missed all three.`;
  } else {
    const what = r.jump > 0 ? `a ${r.jump.toFixed(1)}% jump` : "the same weight again after a miss";
    note = `<strong>${per100} of every 100</strong> lifters in your spot made ${what}.`;
    if (r.bomb != null) note += ` Missing it means no ${state.lifter.lift.toLowerCase()} today: <strong>${pct(r.bomb, 1)}</strong> risk.`;
    if (r.jump > 0 && state.attempts[n - 1] && !state.attempts[n - 1].made) {
      note += " Going up after a miss only looks safer: lifters who do it usually judged the miss wasn't about strength.";
    }
    if (r.rare) note += " Few lifters jump this much, and the ones who do usually felt strong, so treat these odds as optimistic.";
    if (r.maximin) note += " A 3–4.5% third-attempt jump has the best worst-case expected gain in our research.";
  }
  if (state.example && n === 0) note = `<em>Example: a lifter with a ${EXAMPLE_BEST} kg previous best. Enter yours under “You”.</em> ${note}`;
  $("platform-note").innerHTML = note;
  renderBarbell(w);
}

function renderSummary() {
  const l = state.lifter;
  const bits = [l.lift, l.equip, l.sex === "F" ? "Women" : "Men", l.best ? `best ${fmtKg(l.best)} kg` : "no previous best"];
  $("lifter-summary").textContent = bits.join(" · ");
}

function render() {
  const n = nextIndex();
  renderAttempts(n);
  renderOptions(n);
  renderPlatform(n);
  renderSummary();
}

// ---------- state changes ----------

function resetSelection() {
  state.custom = false;
  const n = nextIndex();
  state.selected = n < 3 ? defaultWeight(n) : null;
}

function readForm() {
  const data = new FormData(form);
  const num = (k) => {
    const v = parseFloat(data.get(k));
    return Number.isFinite(v) ? v : null;
  };
  Object.assign(state.lifter, {
    lift: data.get("lift"),
    best: num("best") && num("best") >= 20 ? num("best") : null,
    sex: data.get("sex"),
    equip: data.get("equip"),
    priorMeets: Math.max(0, Math.round(num("priorMeets") ?? 0)),
    age: num("age"),
    federation: data.get("federation"),
    tested: data.get("tested") === "on",
    singleLift: data.get("singleLift") === "on",
  });
  if (state.example) return; // don't remember the sample lifter as the user's profile
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state.lifter)); } catch { /* storage unavailable */ }
}

function writeForm() {
  const l = state.lifter;
  for (const key of ["lift", "sex", "equip"]) {
    const input = form.querySelector(`input[name="${key}"][value="${l[key]}"]`);
    if (input) input.checked = true;
  }
  form.best.value = l.best ?? "";
  form.priorMeets.value = l.priorMeets;
  form.age.value = l.age ?? "";
  form.federation.value = l.federation;
  form.tested.checked = l.tested;
  form.singleLift.checked = l.singleLift;
}

function init() {
  const select = $("federation");
  for (const fed of [...payload.federations].sort((a, b) => a.localeCompare(b))) {
    select.add(new Option(fed, fed));
  }
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (saved) Object.assign(state.lifter, saved);
    else state.example = true;
  } catch {
    state.example = true;
  }
  if (state.example) state.lifter.best = EXAMPLE_BEST;
  writeForm();
  if (window.matchMedia("(max-width: 900px)").matches && state.lifter.best) $("lifter").open = false;

  form.addEventListener("input", (e) => {
    if (e.target.name === "best") state.example = false;
    readForm();
    if (!state.custom || e.target.name === "lift" || e.target.name === "best") resetSelection();
    render();
  });
  form.addEventListener("submit", (e) => e.preventDefault());

  $("step").addEventListener("change", (e) => {
    state.step = parseFloat(e.target.value);
    if (!state.custom) resetSelection();
    render();
  });

  $("options").addEventListener("click", (e) => {
    const btn = e.target.closest(".option");
    if (!btn) return;
    state.selected = parseFloat(btn.dataset.w);
    state.custom = true;
    render();
  });

  $("attempts").addEventListener("input", (e) => {
    if (!e.target.classList.contains("attempt-input")) return;
    const v = parseFloat(e.target.value);
    state.selected = Number.isFinite(v) && v >= 20 ? v : null;
    state.custom = true;
    renderOptions(nextIndex());
    renderPlatform(nextIndex());
    document.querySelectorAll(".judge").forEach((b) => { b.disabled = !state.selected; });
  });

  $("attempts").addEventListener("click", (e) => {
    const judge = e.target.closest("[data-result]");
    const undo = e.target.closest("[data-undo]");
    if (judge && state.selected) {
      const n = nextIndex();
      const prev = state.attempts[n - 1];
      if (prev && state.selected < prev.w) return;
      state.attempts[n] = { w: state.selected, made: judge.dataset.result === "good" };
      resetSelection();
      render();
    } else if (undo) {
      const i = Number(undo.dataset.undo);
      state.selected = state.attempts[i].w;
      state.custom = true;
      state.attempts[i] = null;
      render();
    }
  });

  readForm();
  resetSelection();
  render();
}

init();
