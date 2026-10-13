// Browser/Node mirror of analysis/features.py: builds the same features and applies the exported
// logistic models. tests/predict.test.mjs checks it against Python predictions.

function clip(x, [lo, hi]) {
  return Math.min(hi, Math.max(lo, x));
}

function hinge(out, x, knots, range, name) {
  const v = clip(x, range);
  out[name] = v;
  for (const k of knots) out[`${name}_h${k}`] = Math.max(0, v - k);
}

/**
 * @param {object} spec  model.json "spec"
 * @param {string[]} federations  model.json "federations"
 * @param {object} c  situation:
 *   attempt (1|2|3), pct (% of previous best, or null), jump (% over previous attempt),
 *   prevMiss, a1Miss (booleans), j12 (% jump from 1st to 2nd), female, equip ("Raw"|"Wraps"|"Equipped"),
 *   tested, singleLift (booleans), priorMeets (number), age (number or null), federation (string)
 */
export function buildFeatures(spec, federations, c) {
  const f = {};
  if (c.pct != null) hinge(f, c.pct, spec.pct_knots, spec.pct_clip, "pct");
  if (c.attempt >= 2) {
    hinge(f, c.jump, spec.jump_knots, spec.jump_clip, "jump");
    f.prev_miss = c.prevMiss ? 1 : 0;
    f.prev_miss_x_jump = f.prev_miss * clip(c.jump, spec.jump_clip);
  }
  if (c.attempt === 3) {
    f.a1_miss = c.a1Miss ? 1 : 0;
    hinge(f, c.j12, spec.j12_knots, spec.jump_clip, "j12");
  }
  f.female = c.female ? 1 : 0;
  f.wraps = c.equip === "Wraps" ? 1 : 0;
  f.equipped = c.equip === "Equipped" ? 1 : 0;
  f.tested = c.tested ? 1 : 0;
  f.single_lift_event = c.singleLift ? 1 : 0;
  for (const [lo, hi] of spec.exp_bins.slice(1)) {
    f[`exp_${lo}_${hi}`] = c.priorMeets >= lo && c.priorMeets <= hi ? 1 : 0;
  }
  for (const [lo, hi] of spec.age_bins) {
    if (lo === 24) continue; // reference group (also used when age is unknown)
    f[`age_${Math.trunc(lo)}_${Math.trunc(hi)}`] = c.age != null && c.age >= lo && c.age <= hi ? 1 : 0;
  }
  for (const name of federations) f[`fed_${name}`] = c.federation === name ? 1 : 0;
  return f;
}

export function modelFor(payload, lift, attempt, hasBest) {
  return payload.models[`${lift}_${attempt}_${hasBest ? "pb" : "nopb"}`];
}

/** Chance (0-1) of making an attempt in situation c. */
export function chance(payload, lift, c) {
  const model = modelFor(payload, lift, c.attempt, c.pct != null);
  const f = buildFeatures(payload.spec, payload.federations, c);
  let z = model.intercept;
  model.features.forEach((name, i) => {
    if (!(name in f)) throw new Error(`missing feature ${name}`);
    z += model.coef[i] * f[name];
  });
  return 1 / (1 + Math.exp(-z));
}

/** Chance of missing all three attempts when opening at a weight and repeating it after each miss. */
export function bombOutRisk(payload, lift, base) {
  const miss1 = 1 - chance(payload, lift, { ...base, attempt: 1 });
  const miss2 = 1 - chance(payload, lift, { ...base, attempt: 2, jump: 0, prevMiss: true });
  const miss3 = 1 - chance(payload, lift, { ...base, attempt: 3, jump: 0, prevMiss: true, a1Miss: true, j12: 0 });
  return miss1 * miss2 * miss3;
}
