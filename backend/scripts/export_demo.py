"""Run the demo scenario (scripted breakdown) for both strategies and save artifacts.

Usage: python -m scripts.export_demo  -> writes ../results/
"""

from __future__ import annotations

import json
from pathlib import Path

from fleet.engine import log_as_dicts, metrics, run_to_end, start
from fleet.scenario import load_scenario
from llm.assistant import template_explanation
from scripts.benchmark import run_benchmark

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    scenario = load_scenario(ROOT / "backend" / "scenario.json")
    demo = {}
    for strategy in ("baseline", "edf", "coordinator"):
        run = run_to_end(start(scenario, strategy))
        log = log_as_dicts(run)
        for entry in log:
            if entry["kind"] == "replan":
                entry["explanation"] = template_explanation(entry["data"]["diff"]).model_dump()
        demo[strategy] = {"metrics": metrics(run), "log": log}
    (RESULTS / "demo_event_log.json").write_text(json.dumps(demo, indent=2))

    bench = run_benchmark(50)
    (RESULTS / "benchmark.json").write_text(json.dumps(bench, indent=2))
    keys = ("jobs_completed", "priority1_completed", "priority_score", "travel_hours", "idle_hours", "refuel_stops", "invariant_violations")
    s = bench["summary"]
    lines = ["| metric (mean of 50) | coordinator | EDF | FCFS |", "|---|---|---|---|"]
    lines += [f"| {k} | {s['coordinator'].get(k, '')} | {s['edf'].get(k, '')} | {s['baseline'].get(k, '')} |" for k in keys]
    for label, v in (("vs FCFS", bench), ("vs EDF", bench["vs_edf"]), ("vs EDF, priority-weighted", bench["vs_edf_priority"])):
        lines.append(f"\n{label}: wins {v['wins']} · ties {v['ties']} · losses {v['losses']}")
    lines.append("\nDemo scenario (T1 breaks down at 08:00):\n\n| metric | coordinator | EDF | FCFS |\n|---|---|---|---|")
    lines += [
        f"| {k} | {demo['coordinator']['metrics'][k]} | {demo['edf']['metrics'][k]} | {demo['baseline']['metrics'][k]} |"
        for k in keys
    ]
    (RESULTS / "comparison.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
