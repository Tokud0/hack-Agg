"""Coordinator vs two greedy baselines over N seeded random scenarios.

Baselines: first-come-first-served and earliest-deadline-first.
Usage: python -m scripts.benchmark [--n 50] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from statistics import mean

from fleet.engine import metrics, run_to_end, start
from fleet.scenario import random_scenario

COLUMNS = ("jobs_completed", "priority1_completed", "priority_score", "travel_hours", "travel_per_job", "idle_hours", "refuel_stops", "invariant_violations")
STRATEGIES = ("coordinator", "baseline", "edf")


def _versus(rows: list[dict], other: str, key: str = "jobs_completed") -> dict:
    ours = [r["coordinator"][key] for r in rows]
    theirs = [r[other][key] for r in rows]
    wins = sum(a > b for a, b in zip(ours, theirs))
    ties = sum(a == b for a, b in zip(ours, theirs))
    return {"wins": wins, "ties": ties, "losses": len(rows) - wins - ties}


def run_benchmark(n: int) -> dict:
    rows = []
    for seed in range(n):
        scenario = random_scenario(seed)
        rows.append({"seed": seed, **{s: metrics(run_to_end(start(scenario, s))) for s in STRATEGIES}})
    summary = {s: {col: round(mean(r[s][col] for r in rows), 2) for col in COLUMNS} for s in STRATEGIES}
    for s in STRATEGIES:  # per job over the whole benchmark, so shifts with no finished job cannot skew it
        done = sum(r[s]["jobs_completed"] for r in rows)
        summary[s]["travel_per_job"] = round(sum(r[s]["travel_hours"] for r in rows) / done, 2) if done else 0.0
    summary["coordinator"]["invariant_violations_total"] = sum(r["coordinator"]["invariant_violations"] for r in rows)
    vs_fcfs = _versus(rows, "baseline")
    return {
        "n": n,
        "summary": summary,
        **vs_fcfs,
        "vs_edf": _versus(rows, "edf"),
        "vs_edf_priority": _versus(rows, "edf", "priority_score"),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    result = run_benchmark(args.n)
    out = sys.stdout
    out.write(f"\nBenchmark over {result['n']} random scenarios (same breakdowns for all)\n\n")
    out.write(f"{'metric (mean)':<24}{'coordinator':>14}{'FCFS':>10}{'EDF':>10}\n")
    for col in COLUMNS:
        s = result["summary"]
        out.write(f"{col:<24}{s['coordinator'][col]:>14}{s['baseline'][col]:>10}{s['edf'][col]:>10}\n")
    out.write(f"\nvs FCFS: wins {result['wins']}, ties {result['ties']}, losses {result['losses']}\n")
    e = result["vs_edf"]
    out.write(f"vs EDF:  wins {e['wins']}, ties {e['ties']}, losses {e['losses']}\n")
    p = result["vs_edf_priority"]
    out.write(f"vs EDF (priority-weighted): wins {p['wins']}, ties {p['ties']}, losses {p['losses']}\n")
    out.write(f"Invariant violations total: {result['summary']['coordinator']['invariant_violations_total']}\n")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
