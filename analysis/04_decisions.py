"""Decision analysis: the expected-kg-optimal third attempt, and carry-over after misses.

Usage: uv run python analysis/04_decisions.py
"""

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from common import FIGURES, HOLDOUT_START, LIFT_COLORS, LIFTS, RESULTS, ROOT, load_sample, save_json, style, wilson
from features import add_entry_context, build_features

style()
JUMP_GRID = np.round(np.arange(0.5, 15.01, 0.5), 2)
N_SCENARIO = 60_000


def predict(model, X):
    X = X[model["features"]]
    return 1 / (1 + np.exp(-(X.to_numpy() @ np.array(model["coef"]) + model["intercept"])))


def mtr_bounds(jump, success, edges):
    """Bounds on P(make the 3rd attempt) if everyone had taken jump bin t, assuming only monotone
    treatment response (a heavier bar on the same day is never easier; Manski 1997).
    Lifters who chose a bigger jump and made it would have made a smaller one; lifters who chose a
    smaller jump and missed would have missed a bigger one; everyone else is unknown (0 or 1)."""
    z = np.digitize(np.clip(jump, edges[0], edges[-1] - 1e-9), edges[1:-1])
    k = len(edges) - 1
    share = np.array([(z == u).mean() for u in range(k)])
    made = np.array([success[z == u].mean() if (z == u).any() else 0.0 for u in range(k)])
    lo, hi = np.zeros(k), np.zeros(k)
    for t in range(k):
        lo[t] = share[t] * made[t] + sum(share[u] * made[u] for u in range(t + 1, k))
        hi[t] = sum(share[u] * made[u] for u in range(t)) + share[t] * made[t] + share[t + 1:].sum()
    return share, made, lo, hi


def third_attempt(d, payload, out):
    """What can the data say about the third-attempt jump? Observed gains, worst/best-case bounds, and the
    naive model answer that selection produces."""
    feds = payload["federations"]
    a3 = d[(d["Attempt"] == 3) & (d["PrevSuccess"] == True) & d["A1Success"]].copy()
    edges = np.array([0, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 9, 11, 13, 15])
    a3 = a3[a3["JumpPct"] < edges[-1]]
    mids = (edges[:-1] + edges[1:]) / 2
    rows, summary = [], []
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    for ax, lift in zip(axes, LIFTS):
        x = a3[a3["Lift"] == lift]
        share, made, lo, hi = mtr_bounds(x["JumpPct"].to_numpy(), x["Success"].to_numpy(), edges)
        gain_lo, gain_hi, gain_obs = mids * lo, mids * hi, mids * made
        maximin = int(np.argmax(gain_lo))
        for t in range(len(mids)):
            rows.append({"lift": lift, "jump_mid": mids[t], "share": share[t], "made_observed": made[t],
                         "p_lo": lo[t], "p_hi": hi[t], "gain_pct_lo": gain_lo[t], "gain_pct_hi": gain_hi[t]})

        # Naive model answer: plug every jump into the success model for real 2025-26 lifters.
        pop = x[x["PriorBest"].notna() & (x["Date"] >= HOLDOUT_START)]
        pop = pop.sample(min(N_SCENARIO, len(pop)), random_state=7)
        pct2 = pop["PctOfPriorBest"] / (1 + pop["JumpPct"] / 100)
        naive = []
        for j in JUMP_GRID:
            s = pop.assign(JumpPct=j, PctOfPriorBest=pct2 * (1 + j / 100))
            naive.append((predict(payload["models"][f"{lift}_3_pb"], build_features(s, 3, True, feds=feds)) * j).mean())
        summary.append({
            "lift": lift, "n": len(x), "maximin_jump_bin": f"{edges[maximin]}-{edges[maximin + 1]}",
            "maximin_gain_pct_lo": round(gain_lo[maximin], 3),
            "observed_gain_pct_peak_bin": f"{edges[np.argmax(gain_obs)]}-{edges[np.argmax(gain_obs) + 1]}",
            "naive_model_best_jump": float(JUMP_GRID[int(np.argmax(naive))]),
        })

        c = LIFT_COLORS[lift]
        ax.fill_between(mids, gain_lo, gain_hi, color=c, alpha=0.15, label="Possible range (bounds)")
        ax.plot(mids, gain_lo, color=c, lw=1.5, label="Worst case")
        ax.plot(mids, gain_obs, "o", ms=4, color=c, alpha=0.6, label="What lifters who chose it got")
        ax.axvline(mids[maximin], color=c, ls="--", lw=0.8)
        ax.annotate(f"best worst case:\n+{edges[maximin]:g}–{edges[maximin + 1]:g}%", (mids[maximin], gain_lo[maximin]),
                    xytext=(10, 14), textcoords="offset points", fontsize=8)
        ax.set_title(lift)
        ax.set_xlim(0, 15)
        ax.set_ylim(0, None)
    axes[0].set_ylabel("Expected gain, % of 2nd attempt")
    axes[0].legend(loc="upper left", fontsize=7.5)
    fig.supxlabel("Third-attempt jump over a made second attempt (%)", y=-0.04, fontsize=10)
    fig.suptitle("What the data can and cannot say about the third attempt", fontweight="bold", y=1.02)
    fig.savefig(FIGURES / "fig7_third_attempt.png")
    plt.close(fig)
    out["third_attempt"] = summary
    out["third_attempt_bounds"] = pd.DataFrame(rows).round(4).to_dict("records")


def carry_over(d, out):
    """Does missing earlier lifts predict missing the deadlift opener, beyond weight and the day's form?"""
    sbd = d[(d["Event"] == "SBD") & d["PriorBest"].notna()]
    wide = sbd.pivot_table(index=["Name", "MeetID", "Lift"], columns="Attempt",
                           values=["Weight", "Success"], aggfunc="first")
    wide.columns = [f"{a}{b}" for a, b in wide.columns]
    wide = wide.reset_index()
    pb = sbd.groupby(["Name", "MeetID", "Lift"])["PriorBest"].first().rename("PB").reset_index()
    wide = wide.merge(pb, on=["Name", "MeetID", "Lift"])
    w = wide.pivot_table(index=["Name", "MeetID"], columns="Lift",
                         values=["Weight1", "Weight2", "Weight3", "Success1", "Success2", "Success3", "PB"],
                         aggfunc="first")
    w.columns = [f"{lift}_{v}" for v, lift in w.columns]
    w = w.dropna()
    meta = sbd[sbd["Lift"] == "Deadlift"].drop_duplicates(["Name", "MeetID"]).set_index(["Name", "MeetID"])
    w = w.join(meta[["Sex", "EquipGroup", "Tested", "PriorMeets", "Age"]], how="inner")

    def lift_stats(lift):
        made = w[[f"{lift}_Success{i}" for i in (1, 2, 3)]].astype(bool).to_numpy()
        wt = w[[f"{lift}_Weight{i}" for i in (1, 2, 3)]].to_numpy()
        best = np.where(made, wt, 0).max(axis=1)
        return made, 100 * best / w[f"{lift}_PB"].to_numpy(), 100 * wt.max(axis=1) / w[f"{lift}_PB"].to_numpy()

    sq_made, sq_best, sq_max = lift_stats("Squat")
    bn_made, bn_best, bn_max = lift_stats("Bench")
    keep = sq_made.any(axis=1) & bn_made.any(axis=1)  # still in the meet
    w = w[keep]
    sq_made, sq_best, sq_max = sq_made[keep], sq_best[keep], sq_max[keep]
    bn_made, bn_best, bn_max = bn_made[keep], bn_best[keep], bn_max[keep]

    misses = (~sq_made).sum(axis=1) + (~bn_made).sum(axis=1)
    early = (~sq_made[:, :2]).sum(axis=1) + (~bn_made[:, :2]).sum(axis=1)
    third = (~sq_made[:, 2]).astype(int) + (~bn_made[:, 2]).astype(int)
    y = w["Deadlift_Success1"].astype(bool).to_numpy().astype(float)
    open_pct = np.clip(100 * w["Deadlift_Weight1"].to_numpy() / w["Deadlift_PB"].to_numpy(), 70, 125)

    base = pd.DataFrame({
        "open_pct": open_pct, "open_h90": np.maximum(0, open_pct - 90), "open_h95": np.maximum(0, open_pct - 95),
        "open_h100": np.maximum(0, open_pct - 100),
        "female": (w["Sex"] == "F").astype(float).to_numpy(),
        "wraps": (w["EquipGroup"] == "Wraps").astype(float).to_numpy(),
        "equipped": (w["EquipGroup"] == "Equipped").astype(float).to_numpy(),
        "tested": w["Tested"].astype(float).to_numpy(),
        "log_meets": np.log1p(w["PriorMeets"].to_numpy()),
    })
    form = pd.DataFrame({
        "sq_best_pct": np.clip(sq_best, 70, 125), "bn_best_pct": np.clip(bn_best, 70, 125),
        "sq_max_pct": np.clip(sq_max, 70, 125), "bn_max_pct": np.clip(bn_max, 70, 125),
    })
    miss = pd.DataFrame({"early_misses": early.astype(float), "third_misses": third.astype(float)})

    results = {}
    for label, X in (("weight_only", pd.concat([base, miss], axis=1)),
                     ("plus_day_form", pd.concat([base, form, miss], axis=1))):
        # Standard errors clustered by lifter: the same person appears at many meets.
        groups = pd.factorize(w.index.get_level_values("Name"))[0]
        fit = sm.Logit(y, sm.add_constant(X)).fit(disp=0, cov_type="cluster", cov_kwds={"groups": groups})
        ci = fit.conf_int()
        results[label] = {
            k: {"odds_ratio": round(float(np.exp(fit.params[k])), 4),
                "ci95": [round(float(np.exp(ci.loc[k, 0])), 4), round(float(np.exp(ci.loc[k, 1])), 4)],
                "p": float(fit.pvalues[k])}
            for k in ("early_misses", "third_misses")
        }
    out["carry_over_deadlift_opener"] = {"n_entries": int(len(y)), **results}

    t = pd.DataFrame({"m": np.minimum(misses, 4), "y": y}).groupby("m")["y"].agg(["sum", "size"]).reset_index()
    t["rate"] = t["sum"] / t["size"]
    t["lo"], t["hi"] = wilson(t["sum"], t["size"])
    out["deadlift_opener_by_misses"] = t[["m", "rate", "size"]].round(4).to_dict("records")
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    c = LIFT_COLORS["Deadlift"]
    ax.set_ylim(89, 97.5)
    ax.errorbar(t["m"], 100 * t["rate"], yerr=[100 * (t["rate"] - t["lo"]), 100 * (t["hi"] - t["rate"])],
                fmt="o-", color=c, capsize=3)
    ax.set_xticks(range(5), ["0", "1", "2", "3", "4+"])
    ax.set_xlabel("Misses earlier in the meet (squat + bench)")
    ax.set_ylabel("Deadlift opener made (%)")
    e, t3 = results["plus_day_form"]["early_misses"], results["plus_day_form"]["third_misses"]
    ax.set_title("Misses earlier in the meet predict a shakier deadlift opener")
    ax.text(0.02, 0.03, "Odds of making the opener, adjusted for its weight and the day's form:\n"
            f"×{e['odds_ratio']:.2f} per miss on a 1st/2nd attempt, ×{t3['odds_ratio']:.2f} per 3rd-attempt miss",
            transform=ax.transAxes, fontsize=8, va="bottom")
    fig.savefig(FIGURES / "fig8_carry_over.png")
    plt.close(fig)


def robustness(d, out):
    """Maximin third-attempt jump on a finer grid and within subgroups."""
    a3 = d[(d["Attempt"] == 3) & (d["PrevSuccess"] == True) & d["A1Success"]]
    coarse = np.array([0, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 9, 11, 13, 15])
    fine = np.round(np.arange(0, 15.01, 0.5), 2)

    def maximin(x, edges):
        x = x[x["JumpPct"] < edges[-1]]
        _, _, lo, _ = mtr_bounds(x["JumpPct"].to_numpy(), x["Success"].to_numpy(), edges)
        mids = (edges[:-1] + edges[1:]) / 2
        k = int(np.argmax(mids * lo))
        return f"{edges[k]:g}-{edges[k + 1]:g}"

    groups = {
        "Men": lambda x: x["Sex"] == "M", "Women": lambda x: x["Sex"] == "F",
        "Raw": lambda x: x["EquipGroup"] == "Raw", "Wraps": lambda x: x["EquipGroup"] == "Wraps",
        "Equipped": lambda x: x["EquipGroup"] == "Equipped",
        "0-1 prior meets": lambda x: x["PriorMeets"] <= 1, "8+ prior meets": lambda x: x["PriorMeets"] >= 8,
        "2020 and later": lambda x: x["Year"] >= 2020, "IPF affiliates": lambda x: x["ParentFederation"] == "IPF",
    }
    rows = []
    for lift in LIFTS:
        x = a3[a3["Lift"] == lift]
        row = {"lift": lift, "All (0.5% grid)": maximin(x, fine)}
        row.update({name: maximin(x[f(x)], coarse) for name, f in groups.items()})
        rows.append(row)
    out["third_attempt_robustness"] = rows


def bomb_chain_check(d, payload, out):
    """Validate the calculator's bomb-out risk (open, then repeat after each miss) on 2025-26 meets."""
    feds = payload["federations"]
    made = d.groupby("EntryID")["Success"].sum()
    op = d[(d["Attempt"] == 1) & d["PriorBest"].notna() & (d["Date"] >= HOLDOUT_START)].copy()
    op["Bomb"] = made.reindex(op["EntryID"]).eq(0).to_numpy()
    rows = []
    for lift in LIFTS:
        x = op[op["Lift"] == lift]
        miss = [1 - predict(payload["models"][f"{lift}_{a}_pb"], build_features(s, a, True, feds=feds))
                for a, s in ((1, x),
                             (2, x.assign(JumpPct=0.0, PrevSuccess=False)),
                             (3, x.assign(JumpPct=0.0, PrevSuccess=False, A1Success=False, J12Pct=0.0)))]
        rows.append({"lift": lift, "n": len(x), "observed": round(float(x["Bomb"].mean()), 4),
                     "predicted": round(float(np.mean(miss[0] * miss[1] * miss[2])), 4)})
    out["bomb_chain_check"] = rows


def jump_shares(d):
    """How often lifters choose each 1%-wide jump after a made attempt (shown in the calculator)."""
    a = d[(d["Attempt"] > 1) & (d["PrevSuccess"] == True)]
    shares = {}
    for (lift, attempt), part in a.groupby(["Lift", "Attempt"]):
        counts = np.histogram(np.clip(part["JumpPct"], 0, 30), bins=np.arange(0, 31))[0]
        shares[f"{lift}_{attempt}"] = [round(float(c), 5) for c in counts / counts.sum()]
    return shares


def main():
    payload = json.loads((RESULTS / "model.json").read_text())
    d = add_entry_context(load_sample())
    out = {}
    third_attempt(d, payload, out)
    carry_over(d, out)
    robustness(d, out)
    bomb_chain_check(d, payload, out)
    context = {"jump_shares": jump_shares(d), "maximin_band": [3.0, 4.5]}
    (ROOT / "web/context.json").write_text(json.dumps(context))
    save_json("decisions.json", out)
    print(json.dumps({k: v for k, v in out.items() if k != "third_attempt_bounds"}, indent=1))


if __name__ == "__main__":
    main()
