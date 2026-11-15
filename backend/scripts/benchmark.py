"""Coordinator vs first-come-first-served baseline over N seeded random scenarios.

Usage: python -m scripts.benchmark [--n 50] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from statistics import mean

from fleet.engine import metrics, run_to_end, start
from fleet.scenario import random_scenario

COLUMNS = ("jobs_completed", "priority1_completed", "travel_hours", "idle_hours", "invariant_violations")


def run_benchmark(n: int) -> dict:
    rows = []
    for seed in range(n):
        scenario = random_scenario(seed)
        rows.append(
            {
                "seed": seed,
                "coordinator": metrics(run_to_end(start(scenario, "coordinator"))),
                "baseline": metrics(run_to_end(start(scenario, "baseline"))),
            }
        )
    summary = {
        strategy: {col: round(mean(r[strategy][col] for r in rows), 2) for col in COLUMNS}
        for strategy in ("coordinator", "baseline")
    }
    summary["coordinator"]["invariant_violations_total"] = sum(r["coordinator"]["invariant_violations"] for r in rows)
    wins = sum(r["coordinator"]["jobs_completed"] > r["baseline"]["jobs_completed"] for r in rows)
    ties = sum(r["coordinator"]["jobs_completed"] == r["baseline"]["jobs_completed"] for r in rows)
    return {"n": n, "summary": summary, "wins": wins, "ties": ties, "losses": n - wins - ties, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    result = run_benchmark(args.n)
    out = sys.stdout
    out.write(f"\nBenchmark over {result['n']} random scenarios (same breakdowns for both)\n\n")
    out.write(f"{'metric (mean)':<24}{'coordinator':>14}{'baseline':>12}\n")
    for col in COLUMNS:
        out.write(f"{col:<24}{result['summary']['coordinator'][col]:>14}{result['summary']['baseline'][col]:>12}\n")
    out.write(
        f"\nJobs completed: coordinator wins {result['wins']}, ties {result['ties']}, "
        f"loses {result['losses']}. Invariant violations total: "
        f"{result['summary']['coordinator']['invariant_violations_total']}\n"
    )
    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2)


if __name__ == "__main__":
    main()
