"""Build an attempt-level table from the raw OpenPowerlifting CSV.

One output row = one competition attempt (lifter x meet x lift x attempt number),
with the previous attempt, the jump, the lifter's prior competition best and
their competition experience attached.

Usage: uv run python analysis/01_prepare.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = next((ROOT / "data/raw").glob("openpowerlifting-*/openpowerlifting-*.csv"))
OUT = ROOT / "data/processed"
OUT.mkdir(parents=True, exist_ok=True)

LIFTS = ["Squat", "Bench", "Deadlift"]
ATTEMPT_COLS = [f"{lift}{i}Kg" for lift in LIFTS for i in (1, 2, 3)]
BEST_COLS = [f"Best3{lift}Kg" for lift in LIFTS]
EQUIP_GROUP = {
    "Raw": "Raw",
    "Straps": "Raw",
    "Wraps": "Wraps",
    "Single-ply": "Equipped",
    "Multi-ply": "Equipped",
    "Unlimited": "Equipped",
}


def load() -> pd.DataFrame:
    cols = [
        "Name", "Sex", "Event", "Equipment", "Age", "BodyweightKg",
        *ATTEMPT_COLS, *BEST_COLS, "TotalKg", "Place", "Tested", "Country",
        "Federation", "ParentFederation", "Date", "MeetCountry", "MeetName",
    ]
    df = pd.read_csv(RAW, usecols=cols, engine="pyarrow")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Name"])
    df["EquipGroup"] = df["Equipment"].map(EQUIP_GROUP)
    df["MeetID"] = (
        df["Federation"].astype(str) + "|" + df["Date"].dt.strftime("%Y-%m-%d")
        + "|" + df["MeetCountry"].astype(str) + "|" + df["MeetName"].astype(str)
    )
    df["Tested"] = df["Tested"].eq("Yes")
    return df


def add_experience(df: pd.DataFrame) -> pd.DataFrame:
    """Number of distinct earlier meet dates for each lifter (any federation)."""
    dates = df[["Name", "Date"]].drop_duplicates().sort_values(["Name", "Date"])
    dates["PriorMeets"] = dates.groupby("Name").cumcount()
    first = dates.groupby("Name")["Date"].transform("min")
    dates["YearsCompeting"] = (dates["Date"] - first).dt.days / 365.25
    prev = dates.groupby("Name")["Date"].shift()
    dates["DaysSinceLastMeet"] = (dates["Date"] - prev).dt.days
    return df.merge(dates, on=["Name", "Date"], how="left")


def prior_bests(df: pd.DataFrame) -> pd.DataFrame:
    """Best successful competition lift on strictly earlier dates, per lifter x equipment group x lift."""
    frames = []
    for lift in LIFTS:
        best = df[["Name", "EquipGroup", "Date", f"Best3{lift}Kg"]].rename(columns={f"Best3{lift}Kg": "Best"})
        best = best[best["Best"] > 0]
        best = best.groupby(["Name", "EquipGroup", "Date"], as_index=False)["Best"].max()
        best = best.sort_values(["Name", "EquipGroup", "Date"])
        # Running best up to and including this date; matched to later meets only.
        best["PriorBest"] = best.groupby(["Name", "EquipGroup"])["Best"].cummax()
        best["Lift"] = lift
        frames.append(best[["Name", "EquipGroup", "Date", "Lift", "PriorBest"]])
    return pd.concat(frames, ignore_index=True)


def to_attempts(df: pd.DataFrame) -> pd.DataFrame:
    keep = [
        "Name", "Sex", "Event", "Equipment", "EquipGroup", "Age", "BodyweightKg",
        "Tested", "Country", "Federation", "ParentFederation", "Date", "MeetID",
        "PriorMeets", "YearsCompeting", "DaysSinceLastMeet",
    ]
    frames = []
    for lift in LIFTS:
        a = df[keep + [f"{lift}{i}Kg" for i in (1, 2, 3)]].copy()
        a.columns = keep + ["W1", "W2", "W3"]
        # Only entries where all three attempts were recorded.
        a = a.dropna(subset=["W1", "W2", "W3"])
        a = a[(a[["W1", "W2", "W3"]] != 0).all(axis=1)]
        a["Lift"] = lift
        # Same lifter, same meet, same lift, same attempts = duplicate division entry.
        a = a.drop_duplicates(subset=["Name", "MeetID", "Lift", "W1", "W2", "W3"])
        frames.append(a)
    entries = pd.concat(frames, ignore_index=True)
    entries["EntryID"] = np.arange(len(entries))
    return entries


def main() -> None:
    df = load()
    print(f"raw rows: {len(df):,}")
    df = add_experience(df)
    pb = prior_bests(df)
    entries = to_attempts(df)
    print(f"lift entries with all 3 attempts: {len(entries):,}")

    # Prior best: running best as of the latest strictly earlier date.
    entries = entries.sort_values("Date")
    pb = pb.dropna(subset=["PriorBest"]).sort_values("Date")
    merged = []
    for (lift, eq), part in entries.groupby(["Lift", "EquipGroup"], dropna=False):
        sub = pb[(pb["Lift"] == lift) & (pb["EquipGroup"] == eq)]
        m = pd.merge_asof(
            part, sub[["Name", "Date", "PriorBest"]], on="Date", by="Name",
            direction="backward", allow_exact_matches=False,
        )
        merged.append(m)
    entries = pd.concat(merged, ignore_index=True)

    # Meets that never record a miss are not reporting failures: drop them.
    w = entries[["W1", "W2", "W3"]]
    entries["MeetMisses"] = (w < 0).sum(axis=1)
    meet = entries.groupby("MeetID").agg(n=("EntryID", "size"), misses=("MeetMisses", "sum"))
    bad = meet[(meet["misses"] == 0) & (meet["n"] >= 10)].index
    small = meet[meet["n"] < 10].index
    print(f"meets: {len(meet):,}; dropped no-miss meets: {len(bad):,}; small meets kept: {len(small):,}")
    entries = entries[~entries["MeetID"].isin(bad)].drop(columns="MeetMisses")

    # Long format: one row per attempt.
    long = entries.melt(
        id_vars=[c for c in entries.columns if c not in ("W1", "W2", "W3")],
        value_vars=["W1", "W2", "W3"], var_name="Attempt", value_name="WSigned",
    )
    long["Attempt"] = long["Attempt"].str[1].astype(int)
    long["Weight"] = long["WSigned"].abs()
    long["Success"] = long["WSigned"] > 0
    long = long.sort_values(["EntryID", "Attempt"])
    g = long.groupby("EntryID")
    long["PrevWeight"] = g["Weight"].shift()
    long["PrevSuccess"] = g["Success"].shift()
    long["JumpKg"] = long["Weight"] - long["PrevWeight"]
    long["JumpPct"] = 100 * long["JumpKg"] / long["PrevWeight"]
    long["PctOfPriorBest"] = 100 * long["Weight"] / long["PriorBest"]
    long["Year"] = long["Date"].dt.year
    long = long.drop(columns="WSigned")

    long.to_parquet(OUT / "attempts.parquet", index=False)
    print(f"attempt rows: {len(long):,}  lifters: {long['Name'].nunique():,}  meets: {long['MeetID'].nunique():,}")
    print(f"years: {long['Year'].min()}-{long['Year'].max()}")
    print("success rate by lift x attempt:")
    print(long.pivot_table(index="Lift", columns="Attempt", values="Success", aggfunc="mean").round(3))
    print("jump % quantiles (attempts 2-3):")
    print(long.loc[long["Attempt"] > 1, "JumpPct"].quantile([0.001, 0.01, 0.05, 0.5, 0.95, 0.99, 0.999]).round(2))
    print(f"share with prior best: {long['PriorBest'].notna().mean():.3f}")


if __name__ == "__main__":
    main()
