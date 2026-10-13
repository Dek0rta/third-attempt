"""Shared loading, sample definition and plotting style."""

import json
from pathlib import Path

import matplotlib as mpl
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
FIGURES = ROOT / "figures"
RESULTS = ROOT / "results"
FIGURES.mkdir(exist_ok=True)
RESULTS.mkdir(exist_ok=True)

LIFTS = ["Squat", "Bench", "Deadlift"]
LIFT_COLORS = {"Squat": "#2F6DB5", "Bench": "#D2691E", "Deadlift": "#3A8F5C"}
HOLDOUT_START = pd.Timestamp("2025-01-01")


def load_sample(columns=None) -> pd.DataFrame:
    """Analysis sample: 2000+, men and women, known equipment, plausible weights and jumps."""
    d = pd.read_parquet(PROCESSED / "attempts.parquet", columns=columns)
    keep = (d["Year"] >= 2000) & d["Sex"].isin(["M", "F"]) & d["EquipGroup"].notna()
    keep &= d["Weight"].between(15, 600)
    later = d["Attempt"] > 1
    keep &= ~later | d["JumpPct"].between(0, 30)
    keep &= d["PctOfPriorBest"].isna() | d["PctOfPriorBest"].between(50, 150)
    return d[keep].copy()


def wilson(successes, n, z=1.96):
    """95% Wilson score interval for a binomial proportion."""
    successes, n = np.asarray(successes, float), np.asarray(n, float)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return centre - half, centre + half


def style() -> None:
    mpl.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "font.family": "sans-serif",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.titleweight": "bold",
        "axes.titlesize": 11,
        "legend.frameon": False,
    })


def save_json(name: str, obj) -> None:
    def default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        raise TypeError(type(o))

    (RESULTS / name).write_text(json.dumps(obj, indent=2, default=default))
