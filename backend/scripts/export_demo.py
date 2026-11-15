"""Run the demo scenario (scripted breakdown) for both strategies and save artifacts.

Usage: python -m scripts.export_demo  -> writes ../results/
"""

from __future__ import annotations

import json
from pathlib import Path

from fleet.engine import log_as_dicts, metrics, run_to_end, start
from fleet.scenario import load_scenario
from llm.claude import template_explanation
from scripts.benchmark import run_benchmark

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    scenario = load_scenario(ROOT / "backend" / "scenario.json")
    demo = {}
    for strategy in ("baseline", "coordinator"):
        run = run_to_end(start(scenario, strategy))
        log = log_as_dicts(run)
        for entry in log:
            if entry["kind"] == "replan":
                entry["explanation"] = template_explanation(entry["data"]["diff"]).model_dump()
        demo[strategy] = {"metrics": metrics(run), "log": log}
    (RESULTS / "demo_event_log.json").write_text(json.dumps(demo, indent=2))

    bench = run_benchmark(50)
    (RESULTS / "benchmark.json").write_text(json.dumps(bench, indent=2))
    lines = ["| metric (mean of 50) | coordinator | baseline |", "|---|---|---|"]
    for key in ("jobs_completed", "priority1_completed", "travel_hours", "idle_hours", "invariant_violations"):
        lines.append(f"| {key} | {bench['summary']['coordinator'][key]} | {bench['summary']['baseline'][key]} |")
    lines.append(f"\nWins {bench['wins']} · ties {bench['ties']} · losses {bench['losses']} (jobs completed on time)")
    lines.append("\nDemo scenario:\n\n| metric | coordinator | baseline |\n|---|---|---|")
    for key in ("jobs_completed", "priority1_completed", "travel_hours", "idle_hours", "invariant_violations"):
        lines.append(f"| {key} | {demo['coordinator']['metrics'][key]} | {demo['baseline']['metrics'][key]} |")
    (RESULTS / "comparison.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
