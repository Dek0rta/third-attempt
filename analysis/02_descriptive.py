"""Descriptive results and figures 1-5.

Usage: uv run python analysis/02_descriptive.py
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import FIGURES, LIFT_COLORS, LIFTS, load_sample, save_json, style, wilson

style()


def rate_table(df, by):
    t = df.groupby(by, observed=True)["Success"].agg(["sum", "size"])
    t["rate"] = t["sum"] / t["size"]
    t["lo"], t["hi"] = wilson(t["sum"], t["size"])
    return t.reset_index()


def fig_success_by_attempt(d, out):
    t = rate_table(d, ["Lift", "Attempt"])
    fig, ax = plt.subplots(figsize=(6, 3.6))
    width = 0.26
    for i, lift in enumerate(LIFTS):
        s = t[t["Lift"] == lift]
        x = s["Attempt"] + (i - 1) * width
        ax.bar(x, 100 * s["rate"], width, color=LIFT_COLORS[lift], label=lift)
        for xi, r in zip(x, s["rate"]):
            ax.text(xi, 100 * r + 1, f"{100 * r:.0f}", ha="center", fontsize=8)
    ax.set_xticks([1, 2, 3], ["1st attempt", "2nd attempt", "3rd attempt"])
    ax.set_ylabel("Attempts made (%)")
    ax.set_ylim(0, 105)
    ax.set_title("Success rate falls with every attempt")
    ax.legend(ncol=3, loc="upper right")
    fig.savefig(FIGURES / "fig1_success_by_attempt.png")
    plt.close(fig)
    out["success_by_lift_attempt"] = {
        f"{r.Lift}_{r.Attempt}": round(r.rate, 4) for r in t.itertuples()
    }


def fig_jump_paradox(d, out):
    a = d[(d["Attempt"] > 1) & (d["PrevSuccess"] == True)].copy()
    edges = [0, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 30]
    a["bin"] = pd.cut(a["JumpPct"], edges, include_lowest=True)
    t = rate_table(a, ["Lift", "Attempt", "bin"])
    t = t[t["size"] >= 1000]
    t["mid"] = t["bin"].apply(lambda b: (b.left + b.right) / 2).astype(float)
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), sharey=True)
    for ax, att in zip(axes, (2, 3)):
        for lift in LIFTS:
            s = t[(t["Lift"] == lift) & (t["Attempt"] == att)]
            ax.plot(s["mid"], 100 * s["rate"], "o-", color=LIFT_COLORS[lift], label=lift, ms=4)
            ax.fill_between(s["mid"], 100 * s["lo"], 100 * s["hi"], color=LIFT_COLORS[lift], alpha=0.15)
        ax.set_title(f"{att}{'nd' if att == 2 else 'rd'} attempt, after a made lift")
        ax.set_xlabel("Jump over previous attempt (%)")
    axes[0].set_ylabel("Attempts made (%)")
    axes[0].legend()
    fig.suptitle("The jump paradox: the smallest jumps fail most often", fontweight="bold", y=1.02)
    fig.savefig(FIGURES / "fig2_jump_paradox.png")
    plt.close(fig)
    out["jump_paradox"] = [
        {"lift": r.Lift, "attempt": r.Attempt, "bin": str(r.bin), "rate": round(r.rate, 4), "n": r.size}
        for r in t.itertuples()
    ]


def fig_pct_of_best(d, out):
    p = d[d["PriorBest"].notna()].copy()
    edges = [50, 80, 85, 88, 90, 92, 94, 96, 98, 100, 102, 104, 106, 108, 110, 115, 120]
    p["bin"] = pd.cut(p["PctOfPriorBest"], edges, include_lowest=True)
    t = rate_table(p, ["Lift", "Attempt", "bin"])
    t = t[t["size"] >= 500]
    t["mid"] = t["bin"].apply(lambda b: (b.left + b.right) / 2).astype(float)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    shades = {1: 0.45, 2: 0.7, 3: 1.0}
    for ax, lift in zip(axes, LIFTS):
        for att in (1, 2, 3):
            s = t[(t["Lift"] == lift) & (t["Attempt"] == att)]
            ax.plot(s["mid"], 100 * s["rate"], "o-", ms=3, color=LIFT_COLORS[lift],
                    alpha=shades[att], label=f"Attempt {att}")
        ax.axvline(100, color="grey", lw=0.8, ls="--")
        ax.set_title(lift)
    fig.supxlabel("Attempt weight, % of lifter's previous competition best", y=-0.04, fontsize=10)
    axes[0].set_ylabel("Attempts made (%)")
    axes[0].legend()
    fig.suptitle("Same weight, different odds: later attempts fail more at every load", fontweight="bold", y=1.02)
    fig.savefig(FIGURES / "fig3_pct_of_best.png")
    plt.close(fig)
    out["pct_of_best"] = [
        {"lift": r.Lift, "attempt": r.Attempt, "bin": str(r.bin), "rate": round(r.rate, 4), "n": r.size}
        for r in t.itertuples()
    ]
    pr = p[p["PctOfPriorBest"] > 100]
    out["pr_attempt_success"] = rate_table(pr, ["Lift", "Attempt"]).assign(
        rate=lambda x: x["rate"].round(4)
    )[["Lift", "Attempt", "rate", "size"]].to_dict("records")


def fig_bombout(d, out):
    made = d.groupby("EntryID")["Success"].sum()
    op = d[d["Attempt"] == 1].set_index("EntryID")
    op["Bomb"] = made.reindex(op.index).eq(0)
    out["bomb_rate"] = op.groupby("Lift")["Bomb"].mean().round(4).to_dict()
    op = op[op["PriorBest"].notna()]
    edges = [50, 85, 88, 90, 92, 94, 96, 98, 100, 103, 110]
    op["bin"] = pd.cut(op["PctOfPriorBest"], edges, include_lowest=True)
    t = op.groupby(["Lift", "bin"], observed=True)["Bomb"].agg(["sum", "size"]).reset_index()
    t["rate"] = t["sum"] / t["size"]
    t["lo"], t["hi"] = wilson(t["sum"], t["size"])
    t["mid"] = t["bin"].apply(lambda b: (b.left + b.right) / 2).astype(float)
    t.loc[t["bin"] == t["bin"].cat.categories[0], "mid"] = 82.5  # open-ended "<85%" bin
    fig, ax = plt.subplots(figsize=(6, 3.6))
    for lift in LIFTS:
        s = t[t["Lift"] == lift]
        ax.plot(s["mid"], 100 * s["rate"], "o-", ms=4, color=LIFT_COLORS[lift], label=lift)
        ax.fill_between(s["mid"], 100 * s["lo"], 100 * s["hi"], color=LIFT_COLORS[lift], alpha=0.15)
    ax.set_xlabel("Opener, % of lifter's previous best")
    ax.set_ylabel("Missed all three attempts (%)")
    ax.set_title("Heavy openers multiply the risk of bombing out")
    ax.legend()
    fig.savefig(FIGURES / "fig4_bombout.png")
    plt.close(fig)
    out["bomb_by_opener"] = [
        {"lift": r.Lift, "bin": str(r.bin), "rate": round(r.rate, 4), "n": r.size} for r in t.itertuples()
    ]
    out["opener_median_pct_of_best"] = op.groupby("Lift")["PctOfPriorBest"].median().round(1).to_dict()


def fig_after_miss(d, out):
    a = d[(d["Attempt"] > 1) & (d["PrevSuccess"] == False)].copy()
    a["Choice"] = np.where(a["JumpPct"] == 0, "Repeat the weight", "Go up")
    t = rate_table(a, ["Lift", "Attempt", "Choice"])
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.4), sharey=True)
    for ax, att in zip(axes, (2, 3)):
        s = t[t["Attempt"] == att]
        x = np.arange(len(LIFTS))
        for j, (choice, hatch) in enumerate([("Repeat the weight", ""), ("Go up", "//")]):
            v = [s[(s["Lift"] == l) & (s["Choice"] == choice)]["rate"].iloc[0] for l in LIFTS]
            ax.bar(x + (j - 0.5) * 0.38, 100 * np.array(v), 0.38, hatch=hatch,
                   color=[LIFT_COLORS[l] for l in LIFTS], edgecolor="white", label=choice)
        ax.set_xticks(x, LIFTS)
        ax.set_title(f"Attempt {att} after a miss")
    axes[0].set_ylabel("Attempts made (%)")
    axes[0].legend()
    fig.savefig(FIGURES / "fig5_after_miss.png")
    plt.close(fig)
    out["after_miss"] = t.assign(rate=lambda x: x["rate"].round(4))[
        ["Lift", "Attempt", "Choice", "rate", "size"]
    ].to_dict("records")


def main():
    d = load_sample()
    out = {
        "n_attempts": len(d),
        "n_entries": d["EntryID"].nunique(),
        "n_lifters": d["Name"].nunique(),
        "n_meets": d["MeetID"].nunique(),
        "n_federations": d["Federation"].nunique(),
        "n_meet_countries": d["MeetID"].str.split("|").str[2].nunique(),
        "years": [int(d["Year"].min()), int(d["Year"].max())],
        "share_with_prior_best": round(d["PriorBest"].notna().mean(), 4),
        "overall_success": round(d["Success"].mean(), 4),
    }
    fig_success_by_attempt(d, out)
    fig_jump_paradox(d, out)
    fig_pct_of_best(d, out)
    fig_bombout(d, out)
    fig_after_miss(d, out)
    save_json("descriptive.json", out)
    for k in ("n_attempts", "n_entries", "n_lifters", "n_meets", "n_federations", "n_meet_countries", "years",
              "success_by_lift_attempt", "bomb_rate", "opener_median_pct_of_best", "pr_attempt_success"):
        print(k, out[k])


if __name__ == "__main__":
    main()
