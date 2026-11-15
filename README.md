# Run the Fleet: Fleet Coordinator

A coordinator that assigns jobs to a small fleet of simulated autonomous tractors and **re-plans the moment one breaks down, without losing or duplicating work**. Built for the American Tractor Company "Run the Fleet" track.

- **Algorithm first, LLM second.** Hard constraints (implement, fuel, deadline) are enforced in code. The LLM (Groq `openai/gpt-oss-120b`, with Claude as an alternative) only explains plan changes, answers "why?" and chat questions, narrates what-if forecasts, and turns operator text into typed events or job drafts that the coordinator validates before anything runs.
- **Our own lightweight simulation** (not AgOpenWeb): a 10×10 grid, roads between fields, travel time = distance / speed.
- **One re-plan function for every event**: breakdown, blocked road and changed priority all call `replan(world)`.
- **Provable safety**: invariants are checked after every re-plan. If a check fails, the new plan is thrown away and the last valid one is kept.

## Run it

```bash
# backend (Python 3.11+)
cd backend
python3 -m venv .venv && .venv/bin/pip install fastapi 'uvicorn[standard]' pydantic anthropic python-dotenv pytest pytest-cov httpx
cp .env.example .env            # optional: GROQ_API_KEY (or ANTHROPIC_API_KEY) for AI text
.venv/bin/uvicorn api.main:app --port 8000

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Without an API key everything still works: explanations come from templates, and the copilot and job intake use small offline parsers.

## Dashboard

Five pages, one top bar (run, clock, speed) and one side panel that stay in place:

- **Live**: the coordinator's map (fields fill in as they are worked, fuel rings, planned routes, hand-over arrows after a breakdown), live counters with the lead over the baseline, and a card per tractor with a *Simulate breakdown* button.
- **Agents**: the orchestration pipeline, replayable for every re-plan of the shift (see below).
- **Schedule**: Gantt by tractor (deadlines and events marked) and the full job table, for the coordinator or either baseline.
- **Compare**: baseline (FCFS or EDF) and coordinator side by side on the same shift, plus the 50-shift benchmark.
- **Log**: every event, re-plan and finished job, with event-log export.
- **Side panel**: *Re-plan* (AI explanation and the 4 safety checks of the latest re-plan), *Copilot* chat, *Add jobs* (free text, form or scenario JSON), *Events* (apply a disruption or forecast it with what-if).
- Click any job for **"why?"**: the score breakdown and every rejected alternative.

## Orchestration: ATC's agent layer

The orchestrator follows ATC's suggested architecture. Every event goes through the same pipeline, and every step is recorded in the event log (`trace` and `messages` on each `replan` entry):

| # | Agent | Kind | Job | Limit |
|---|-------|------|-----|-------|
| 1 | Intake (Command Center) | LLM + human | Turns a chat message or a button press into a typed event | Can only propose; the operator confirms |
| 2 | Navigation Agent | Deterministic code | Owns the road map: routes, detours around closed roads, travel times | Every bid uses its travel times |
| 3 | Fleet Agent | Deterministic search | Runs an auction between the tractor agents, in 8 different calling orders, lets them trade, keeps the best result | Same input, same plan; no LLM inside |
| 4 | Safety Agent | Hard rules | Checks the 4 invariants on the winning plan | Has a veto: a failed plan is discarded and the last valid plan stays |
| 5 | Explainer | LLM | Tells the operator what changed and why | Reads the result; cannot change the plan |

### One agent per tractor, and how they talk

Inside the Fleet Agent's step every tractor has its own agent (`backend/fleet/agents.py`). Each answers only for itself (position, fuel, implement, queue), and each re-plan is a conversation in four phases:

1. **Situation**: a broken tractor announces it and releases its jobs; the Navigation Agent reports closed roads and the detour; every other tractor reports where it is and what it keeps.
2. **Auction**: the Fleet Agent calls each job; every tractor replies with a bid (finish time, extra driving) or passes with the reason (wrong implement, fuel, deadline); the best bid wins, the Navigation Agent gives the winner its route, and the winner claims the job so no one else plans for it.
3. **Negotiation**: tractors trade or swap jobs whenever that improves the whole plan.
4. **Approval**: the Safety Agent approves or vetoes; tractors confirm their queues.

The messages are recorded by observing the planner, not written after the fact: a test rebuilds the final plan from the claims and trades alone, and another checks every award went to the lowest bid. Bids are computed by the same feasibility code as the plan, so the benchmark is unchanged. The LLM takes no decisions here; on the Agents page you can pick one tractor and ask its agent a question, and the LLM answers in first person from that agent's own messages (`POST /api/agents/{id}/ask`).

The **Agents** page shows this for any re-plan: the full conversation (filter by agent), what triggered it and who raised it, every auction round with its score before and after trading, the checks, who got which job, the explanation, and the time each step took. *Test the Safety Agent* hands it a deliberately corrupted copy of the live plan (`POST /api/orchestration/fault-test`) and shows the veto; the live plan is not touched.

```bash
cd backend
.venv/bin/pytest --cov=fleet --cov=api --cov=llm   # 61 tests
.venv/bin/python -m scripts.benchmark --n 50       # coordinator vs baseline table
.venv/bin/python -m scripts.export_demo            # writes results/
```

## Results

Our coordinator against two greedy dispatchers that never plan ahead: **FCFS** (first come, first served) and **EDF** (earliest deadline first). All three run the same 50 random scenarios with the same breakdowns (`results/comparison.md`):

| metric (mean of 50) | coordinator | EDF | FCFS |
|---|---|---|---|
| jobs completed on time | **6.30** | 5.88 | 4.80 |
| urgent (P1) jobs completed | **2.52** | 1.96 | 1.70 |
| priority-weighted output | **15.9** | 13.7 | 11.3 |
| driving hours | **6.57** | 7.41 | 7.13 |
| driving hours per completed job | **1.04** | 1.26 | 1.48 |
| idle hours | **0.05** | 0.37 | 0.40 |
| constraint violations | **0** | 0 | 0 |

By jobs completed, the coordinator wins 43, ties 5 and loses 2 against FCFS; against EDF it wins 25, ties 19 and loses 6. On priority-weighted output it wins 39, ties 5 and loses 6 against EDF. The losses happen when a breakdown hits a plan that was optimal before the breakdown.

Demo scenario, with T1 breaking down at 08:00: the coordinator completes 8 jobs, 3 of them urgent, with one refuel stop. EDF completes 7 (2 urgent) and FCFS 7 (1 urgent). It drives more in total than FCFS (11.96 h against 10.66 h) because it does one more job; per completed job it drives slightly less (1.49 h against 1.52 h), and it idles 0.04 h against 0.29 h. Breaking any tractor at any half hour of this shift (48 cases), the coordinator never completes fewer jobs than FCFS and never idles more.

## Deliverables

| Item | Where |
|---|---|
| Scenario (tractors, fields, jobs) | `backend/scenario.json` |
| Event log of the demo run | `results/demo_event_log.json` (also via the "Event log" button) |
| Baseline comparison | `results/comparison.md`, `results/benchmark.json` |

## How the coordinator works (`backend/fleet/`)

1. **Filter** (`feasibility.py`): a tractor's whole queue is simulated in order. Each job needs the right implement, enough fuel for travel plus work, and must finish before its deadline. Inserting a job early can break a later one, so the whole queue is checked every time.
2. **Score and assign** (`coordinator.py`): jobs are sorted by priority, then deadline. Each one goes into the cheapest feasible slot across all queues. The objective is lexicographic: priority-weighted completed work first, then travel, completion time, and time a tractor would wait while another tractor with the same implement still has work queued.
3. **Improve**: multi-start. Several starting plans (by priority, by deadline, by slack, an EDF schedule, and fixed-seed shuffles) are each improved by local search (relocate, swap, insert-unassigned, eject-and-insert) with a fixed iteration cap, and the best one wins. The search is deterministic.
4. **Re-plan on an event** (`replan.py`): completed work is frozen, jobs currently in progress on healthy tractors stay pinned, the finished share of an interrupted job is kept, and everything else is planned again.
5. **Verify** (`invariants.py`): each job has at most one tractor; completed work is never reassigned; every queue satisfies implement, fuel and deadline; every unfinished job is either planned or marked unassignable with a reason.

**Baseline rules** (`baseline.py`): whenever a tractor is free, it takes the first pending job it can feasibly do right now, either in submission order (FCFS) or by earliest deadline (EDF). There is no lookahead. Work released by a breakdown goes back to the pool with its progress kept.

**Metric definitions**: *completed* means done before the deadline. *Idle* is time a healthy tractor sits without work while unfinished, assignable work for its implement is still waiting.

**Fuel and refuelling** (`feasibility.plan_leg`, shared by the planner and the simulator): a tractor always keeps enough fuel to drive back to the depot. That reserve is what lets it take over work after a breakdown. When a job plus the way home does not fit in the tank, the tractor first refuels at the depot (`refuel_hours`, 15 min in the demo). Refuel stops count against deadlines.

## LLM (`backend/llm/`)

`provider.py` uses Groq (`GROQ_MODEL`, default `openai/gpt-oss-120b`, strict JSON-schema output) when `GROQ_API_KEY` is set, otherwise Claude (`claude-opus-5-5`) when `ANTHROPIC_API_KEY` is set, otherwise templates. `assistant.py` holds the features. The model only ever sees structured facts: the plan diff, the score breakdown, the forecast numbers, or a summary of the state. Copilot proposals appear as an "Understood as … Apply / Cancel" card, and every event and job is validated by the coordinator before it runs.
