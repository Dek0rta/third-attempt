"""Feature construction shared by the models, the decision analysis and (mirrored in JS) the web calculator."""

import numpy as np
import pandas as pd

PCT_KNOTS = [85, 90, 95, 100, 105, 110]
PCT_CLIP = (70, 125)
JUMP_KNOTS = [2, 4, 6, 8, 10, 15]
JUMP_CLIP = (0, 25)
J12_KNOTS = [5, 10]
EXP_BINS = [(0, 0), (1, 1), (2, 3), (4, 7), (8, 10_000)]
AGE_BINS = [(0, 17.99), (18, 23.99), (24, 39.99), (40, 49.99), (50, 200)]
MAX_TRAIN = 1_500_000
N_FEDERATIONS = 40
HISTORY_PRIOR = (0.75, 9)  # shrink a lifter's past make-rate toward 75% with the weight of 9 attempts

SPEC = {
    "pct_knots": PCT_KNOTS, "pct_clip": PCT_CLIP,
    "jump_knots": JUMP_KNOTS, "jump_clip": JUMP_CLIP,
    "j12_knots": J12_KNOTS, "exp_bins": EXP_BINS, "age_bins": AGE_BINS,
}


def hinge(x, knots, clip, name):
    x = np.clip(x, *clip)
    cols = {name: x}
    for k in knots:
        cols[f"{name}_h{k}"] = np.maximum(0, x - k)
    return cols


def build_features(df: pd.DataFrame, attempt: int, with_pb: bool, feds=(), history=False) -> pd.DataFrame:
    f = {}
    if with_pb:
        f.update(hinge(df["PctOfPriorBest"].to_numpy(), PCT_KNOTS, PCT_CLIP, "pct"))
    if attempt >= 2:
        f.update(hinge(df["JumpPct"].to_numpy(), JUMP_KNOTS, JUMP_CLIP, "jump"))
        miss = (~df["PrevSuccess"].astype(bool)).to_numpy().astype(float)
        f["prev_miss"] = miss
        f["prev_miss_x_jump"] = miss * np.clip(df["JumpPct"].to_numpy(), *JUMP_CLIP)
    if attempt == 3:
        f["a1_miss"] = (~df["A1Success"].astype(bool)).to_numpy().astype(float)
        f.update(hinge(df["J12Pct"].to_numpy(), J12_KNOTS, JUMP_CLIP, "j12"))
    f["female"] = (df["Sex"] == "F").to_numpy().astype(float)
    f["wraps"] = (df["EquipGroup"] == "Wraps").to_numpy().astype(float)
    f["equipped"] = (df["EquipGroup"] == "Equipped").to_numpy().astype(float)
    f["tested"] = df["Tested"].to_numpy().astype(float)
    f["single_lift_event"] = (df["Event"] != "SBD").to_numpy().astype(float)
    exp = df["PriorMeets"].to_numpy()
    for lo, hi in EXP_BINS[1:]:
        f[f"exp_{lo}_{hi}"] = ((exp >= lo) & (exp <= hi)).astype(float)
    age = df["Age"].to_numpy()
    for lo, hi in AGE_BINS:
        if (lo, hi) == (24, 39.99):
            continue  # reference group; unknown age also falls here
        f[f"age_{int(lo)}_{int(hi)}"] = ((age >= lo) & (age <= hi)).astype(float)
    fed = df["Federation"].to_numpy()
    for name in feds:
        f[f"fed_{name}"] = (fed == name).astype(float)
    if history:
        f["hist_rate"] = df["HistRate"].to_numpy()
        f["hist_log_n"] = np.log1p(df["HistN"].to_numpy())
    return pd.DataFrame(f, index=df.index)


def add_history(d: pd.DataFrame) -> pd.DataFrame:
    """Lifter's make-rate over all attempts at strictly earlier meet dates (shrunk toward the prior)."""
    day = d.groupby(["Name", "Date"])["Success"].agg(["sum", "size"]).sort_index()
    g = day.groupby(level="Name")
    day["HistN"] = g["size"].cumsum() - day["size"]
    succ = g["sum"].cumsum() - day["sum"]
    p0, k = HISTORY_PRIOR
    day["HistRate"] = (succ + p0 * k) / (day["HistN"] + k)
    return d.join(day[["HistN", "HistRate"]], on=["Name", "Date"])


def add_entry_context(d: pd.DataFrame) -> pd.DataFrame:
    """Attach attempt-1 result and the 1->2 jump; keep only entries with all three attempts in the sample."""
    d = d[d.groupby("EntryID")["Attempt"].transform("size") == 3]
    w = d.pivot_table(index="EntryID", columns="Attempt", values="Weight")
    s = d.pivot_table(index="EntryID", columns="Attempt", values="Success")
    ctx = pd.DataFrame({
        "A1Success": s[1].astype(bool),
        "J12Pct": 100 * (w[2] - w[1]) / w[1],
    })
    return d.join(ctx, on="EntryID")
