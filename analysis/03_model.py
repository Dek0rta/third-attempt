"""Attempt-success models, temporal validation and model export for the web calculator.

One logistic model per lift x attempt number, in two variants:
  "pb"   - lifter has a previous competition best in this lift and equipment group
  "nopb" - first competition in this lift / equipment group
Features are hinge (linear-spline) terms so the browser can rebuild them exactly.

Usage: uv run python analysis/03_model.py
"""

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from common import FIGURES, HOLDOUT_START, LIFT_COLORS, LIFTS, RESULTS, ROOT, load_sample, save_json, style
from features import MAX_TRAIN, N_FEDERATIONS, SPEC, add_entry_context, add_history, build_features

style()


def fit(X: pd.DataFrame, y: np.ndarray):
    mu, sd = X.mean(), X.std().replace(0, 1)
    clf = LogisticRegression(C=1.0, max_iter=2000)
    clf.fit(((X - mu) / sd).to_numpy(), y)
    coef = clf.coef_[0] / sd.to_numpy()
    intercept = clf.intercept_[0] - float(np.sum(clf.coef_[0] * mu.to_numpy() / sd.to_numpy()))
    return coef, intercept


def predict(X: pd.DataFrame, coef, intercept):
    return 1 / (1 + np.exp(-(X.to_numpy() @ coef + intercept)))


def main():
    d = load_sample()
    d = add_entry_context(d)
    d = add_history(d)
    train_mask = d["Date"] < HOLDOUT_START
    feds = d.loc[train_mask, "Federation"].value_counts().index[:N_FEDERATIONS].tolist()
    models, metrics, calib = {}, [], []

    for lift in LIFTS:
        for attempt in (1, 2, 3):
            for with_pb in (True, False):
                part = d[(d["Lift"] == lift) & (d["Attempt"] == attempt)]
                part = part[part["PriorBest"].notna() == with_pb]
                tr, te = part[train_mask.loc[part.index]], part[~train_mask.loc[part.index]]
                if len(tr) > MAX_TRAIN:
                    tr = tr.sample(MAX_TRAIN, random_state=7)
                ytr, yte = tr["Success"].to_numpy(), te["Success"].to_numpy()
                # Predictability ladder: calculator inputs, + federation, + lifter's own history.
                ladder = {}
                for label, kw in (("basic", {}), ("federation", {"feds": feds}),
                                  ("history", {"feds": feds, "history": True})):
                    Xtr_, Xte_ = build_features(tr, attempt, with_pb, **kw), build_features(te, attempt, with_pb, **kw)
                    c_, i_ = fit(Xtr_, ytr)
                    ladder[label] = (Xtr_, c_, i_, predict(Xte_, c_, i_))
                Xtr, coef, intercept, p = ladder["federation"]
                base = np.full(len(yte), ytr.mean())
                key = f"{lift}_{attempt}_{'pb' if with_pb else 'nopb'}"
                models[key] = {
                    "features": list(Xtr.columns),
                    "coef": [round(float(c), 6) for c in coef],
                    "intercept": round(float(intercept), 6),
                    "n_train": len(tr),
                }
                m = {
                    "model": key, "n_train": len(tr), "n_test": len(te),
                    "test_rate": round(float(yte.mean()), 4),
                    "auc": round(roc_auc_score(yte, p), 4),
                    "logloss": round(log_loss(yte, p), 4),
                    "logloss_base": round(log_loss(yte, base), 4),
                    "brier": round(brier_score_loss(yte, p), 4),
                    "brier_base": round(brier_score_loss(yte, base), 4),
                }
                m["brier_skill"] = round(1 - m["brier"] / m["brier_base"], 4)
                for label in ("basic", "history"):
                    m[f"auc_{label}"] = round(roc_auc_score(yte, ladder[label][3]), 4)
                metrics.append(m)
                print(m)
                if with_pb:
                    q = pd.qcut(p, 10, duplicates="drop")
                    c = pd.DataFrame({"p": p, "y": yte}).groupby(q, observed=True).mean()
                    for r in c.itertuples():
                        calib.append({"lift": lift, "attempt": attempt, "pred": r.p, "obs": r.y})

    payload = {"spec": SPEC, "federations": feds, "models": models, "holdout_start": str(HOLDOUT_START.date())}
    (ROOT / "web/model.json").write_text(json.dumps(payload))
    (RESULTS / "model.json").write_text(json.dumps(payload, indent=1))
    save_json("model_metrics.json", metrics)

    c = pd.DataFrame(calib)
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True)
    for ax, lift in zip(axes, LIFTS):
        for att, alpha in ((1, 0.45), (2, 0.7), (3, 1.0)):
            s = c[(c["lift"] == lift) & (c["attempt"] == att)]
            ax.plot(100 * s["pred"], 100 * s["obs"], "o-", ms=3, color=LIFT_COLORS[lift], alpha=alpha,
                    label=f"Attempt {att}")
        ax.plot([20, 100], [20, 100], color="grey", lw=0.8, ls="--")
        ax.set_title(lift)
        ax.set_xlim(20, 100)
        ax.set_ylim(20, 100)
    fig.supxlabel("Predicted chance of making the attempt (%)", y=-0.04, fontsize=10)
    axes[0].set_ylabel("Observed share made (%)")
    axes[0].legend()
    fig.suptitle(f"Calibration on unseen meets ({HOLDOUT_START.year}–2026)", fontweight="bold", y=1.02)
    fig.savefig(FIGURES / "fig6_calibration.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
