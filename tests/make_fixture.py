"""Write tests/fixture.json: real 2025-26 situations with Python model predictions, for the JS mirror test.

Usage: uv run python tests/make_fixture.py
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

from common import HOLDOUT_START, LIFTS, load_sample  # noqa: E402
from features import add_entry_context, build_features  # noqa: E402

payload = json.loads((ROOT / "web/model.json").read_text())
d = add_entry_context(load_sample())
d = d[d["Date"] >= HOLDOUT_START]
cases = []
for lift in LIFTS:
    for attempt in (1, 2, 3):
        for with_pb in (True, False):
            part = d[(d["Lift"] == lift) & (d["Attempt"] == attempt) & (d["PriorBest"].notna() == with_pb)]
            part = part.sample(40, random_state=attempt)
            model = payload["models"][f"{lift}_{attempt}_{'pb' if with_pb else 'nopb'}"]
            X = build_features(part, attempt, with_pb, feds=payload["federations"])[model["features"]]
            p = 1 / (1 + np.exp(-(X.to_numpy() @ np.array(model["coef"]) + model["intercept"])))
            for (_, r), prob in zip(part.iterrows(), p):
                cases.append({
                    "lift": lift,
                    "situation": {
                        "attempt": attempt,
                        "pct": float(r["PctOfPriorBest"]) if with_pb else None,
                        "jump": float(r["JumpPct"]) if attempt > 1 else None,
                        "prevMiss": bool(r["PrevSuccess"] == False) if attempt > 1 else None,
                        "a1Miss": bool(not r["A1Success"]) if attempt == 3 else None,
                        "j12": float(r["J12Pct"]) if attempt == 3 else None,
                        "female": r["Sex"] == "F",
                        "equip": r["EquipGroup"],
                        "tested": bool(r["Tested"]),
                        "singleLift": r["Event"] != "SBD",
                        "priorMeets": int(r["PriorMeets"]),
                        "age": None if np.isnan(r["Age"]) else float(r["Age"]),
                        "federation": r["Federation"],
                    },
                    "expected": float(prob),
                })
(ROOT / "tests/fixture.json").write_text(json.dumps(cases))
print(f"{len(cases)} cases")
