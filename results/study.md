# Coordinator against two simple dispatchers

1200 generated shifts (300 in each of four families), every shift run under all three strategies: 3600 simulated shifts in total. On average a shift has 8.5 jobs. Reproduce with `python -m scripts.study --n 300` from `backend/`.

## Headline

- **+26.1% jobs done on time against FCFS**, and +7.4% against EDF.
- **+37.1% urgent jobs** against FCFS.
- **-28.6% idle time** and **-21.4% driving per job** against FCFS; total driving is -1.0%.
- **0 constraint violations** in 1200 shifts.

## All shifts together

Means per shift. The last two columns are the coordinator's difference from each dispatcher; for driving, idle time and jobs not done, a negative number is good.

| Metric | Coordinator | FCFS | EDF | vs FCFS | vs EDF |
|---|---|---|---|---|---|
| Jobs done on time | 6.77 | 5.37 | 6.30 | +26.1% | +7.4% |
| Share of all jobs done on time | 0.793 | 0.629 | 0.738 | +26.1% | +7.4% |
| Urgent (P1) jobs done on time | 2.18 | 1.59 | 1.94 | +37.1% | +12.0% |
| Priority-weighted output | 16.4 | 12.5 | 15.0 | +30.7% | +9.2% |
| Driving, hours | 8.05 | 8.13 | 8.93 | -1.0% | -9.9% |
| Driving per job done, hours | 1.19 | 1.51 | 1.42 | -21.4% | -16.1% |
| Idle, hours | 0.81 | 1.13 | 1.17 | -28.6% | -31.3% |
| Jobs not done | 1.77 | 3.17 | 2.24 | -44.1% | -20.8% |
| Length of the shift, hours | 8.45 | 7.38 | 8.45 | +14.6% | +0.0% |

### Who finishes more jobs, shift by shift

| Against | Coordinator ahead | Level | Coordinator behind |
|---|---|---|---|
| FCFS | 951 (79%) | 230 (19%) | 19 (2%) |
| EDF | 537 (45%) | 592 (49%) | 71 (6%) |

### When the job count is level

The same number of jobs does not mean the same shift. On the shifts where both finished equally many jobs:

**Against FCFS** (230 level shifts): the coordinator is ahead on at least one of priority-weighted output, driving or idle time in 213 (93%) of them.

| Metric | Coordinator better | Same | Coordinator worse |
|---|---|---|---|
| Priority-weighted output | 70 | 128 | 32 |
| Driving | 159 | 22 | 49 |
| Idle time | 172 | 27 | 31 |

**Against EDF** (592 level shifts): the coordinator is ahead on at least one of priority-weighted output, driving or idle time in 562 (95%) of them.

| Metric | Coordinator better | Same | Coordinator worse |
|---|---|---|---|
| Priority-weighted output | 119 | 436 | 37 |
| Driving | 415 | 108 | 69 |
| Idle time | 460 | 38 | 94 |

## By kind of shift

### Benchmark: 10 jobs, 3 tractors, one breakdown, deadlines not adjusted

300 shifts, 10.0 jobs each. By jobs done on time: against FCFS 232 ahead, 59 level, 9 behind; against EDF 131 ahead, 133 level, 36 behind.

| Metric | Coordinator | FCFS | EDF | vs FCFS | vs EDF |
|---|---|---|---|---|---|
| Jobs done on time | 6.24 | 4.95 | 5.84 | +26.1% | +6.8% |
| Share of all jobs done on time | 0.624 | 0.495 | 0.584 | +26.1% | +6.8% |
| Urgent (P1) jobs done on time | 2.48 | 1.66 | 1.94 | +49.4% | +28.1% |
| Priority-weighted output | 15.9 | 11.6 | 13.7 | +37.3% | +16.1% |
| Driving, hours | 6.85 | 7.35 | 7.48 | -6.8% | -8.4% |
| Driving per job done, hours | 1.10 | 1.49 | 1.28 | -26.1% | -14.2% |
| Idle, hours | 0.06 | 0.35 | 0.39 | -83.4% | -84.9% |
| Jobs not done | 3.76 | 5.05 | 4.16 | -25.6% | -9.6% |
| Length of the shift, hours | 7.69 | 7.16 | 7.76 | +7.5% | -0.9% |

### Calm: random shift, nothing goes wrong

300 shifts, 8.1 jobs each. By jobs done on time: against FCFS 269 ahead, 31 level, 0 behind; against EDF 154 ahead, 146 level, 0 behind.

| Metric | Coordinator | FCFS | EDF | vs FCFS | vs EDF |
|---|---|---|---|---|---|
| Jobs done on time | 8.06 | 6.25 | 7.44 | +28.9% | +8.3% |
| Share of all jobs done on time | 1.000 | 0.776 | 0.923 | +28.9% | +8.3% |
| Urgent (P1) jobs done on time | 2.22 | 1.63 | 2.10 | +36.4% | +6.0% |
| Priority-weighted output | 18.8 | 14.3 | 17.5 | +31.5% | +7.6% |
| Driving, hours | 9.27 | 8.90 | 10.21 | +4.1% | -9.2% |
| Driving per job done, hours | 1.15 | 1.42 | 1.37 | -19.3% | -16.2% |
| Idle, hours | 1.18 | 1.60 | 1.68 | -26.4% | -29.7% |
| Jobs not done | 0.00 | 1.81 | 0.62 | -100.0% | -100.0% |
| Length of the shift, hours | 9.28 | 7.59 | 9.07 | +22.2% | +2.2% |

### Some trouble: random shift, one or two events

300 shifts, 8.1 jobs each. By jobs done on time: against FCFS 245 ahead, 54 level, 1 behind; against EDF 133 ahead, 159 level, 8 behind.

| Metric | Coordinator | FCFS | EDF | vs FCFS | vs EDF |
|---|---|---|---|---|---|
| Jobs done on time | 7.13 | 5.64 | 6.64 | +26.3% | +7.3% |
| Share of all jobs done on time | 0.885 | 0.700 | 0.824 | +26.3% | +7.3% |
| Urgent (P1) jobs done on time | 2.15 | 1.61 | 2.04 | +33.5% | +5.6% |
| Priority-weighted output | 17.0 | 13.2 | 15.9 | +29.1% | +6.8% |
| Driving, hours | 8.41 | 8.38 | 9.46 | +0.4% | -11.1% |
| Driving per job done, hours | 1.18 | 1.49 | 1.42 | -20.5% | -17.1% |
| Idle, hours | 1.19 | 1.52 | 1.60 | -22.0% | -25.7% |
| Jobs not done | 0.93 | 2.41 | 1.42 | -61.5% | -34.4% |
| Length of the shift, hours | 8.74 | 7.34 | 8.71 | +19.0% | +0.3% |

### Rough day: random shift, breakdown, closed roads, priority change, weather

300 shifts, 8.1 jobs each. By jobs done on time: against FCFS 205 ahead, 86 level, 9 behind; against EDF 119 ahead, 154 level, 27 behind.

| Metric | Coordinator | FCFS | EDF | vs FCFS | vs EDF |
|---|---|---|---|---|---|
| Jobs done on time | 5.66 | 4.64 | 5.30 | +21.8% | +6.8% |
| Share of all jobs done on time | 0.702 | 0.576 | 0.657 | +21.8% | +6.8% |
| Urgent (P1) jobs done on time | 1.85 | 1.45 | 1.70 | +27.6% | +8.6% |
| Priority-weighted output | 13.8 | 11.1 | 12.9 | +24.5% | +7.2% |
| Driving, hours | 7.65 | 7.87 | 8.57 | -2.8% | -10.7% |
| Driving per job done, hours | 1.35 | 1.70 | 1.62 | -20.2% | -16.4% |
| Idle, hours | 0.80 | 1.03 | 1.03 | -22.9% | -22.5% |
| Jobs not done | 2.40 | 3.41 | 2.76 | -29.7% | -13.0% |
| Length of the shift, hours | 8.11 | 7.41 | 8.25 | +9.4% | -1.7% |

## What each number means

- **Jobs done on time**: a job counts only if it is finished before its own deadline. Mean per shift.
- **Share of all jobs done on time**: the same thing as a fraction of every job in the shift.
- **Urgent (P1) jobs done on time**: the same count, for the highest priority only.
- **Priority-weighted output**: 4 points for an urgent job, 2 for a normal one, 1 for a low one. It shows whether the extra jobs are the important ones.
- **Driving, hours**: total time all tractors spent on the road between fields and the depot.
- **Driving per job done**: driving divided by jobs done on time. A dispatcher that finishes more jobs also drives to more fields, so this is the fair way to compare driving.
- **Idle, hours**: time a healthy tractor stands with nothing to do while unfinished work for its implement is still waiting. A tractor held at a field by the weather is not counted as idle.
- **Jobs not done**: jobs that could not be finished in time (deadline missed, or no working tractor with the right implement).
- **Length of the shift**: when the last piece of work ended. A dispatcher that gives up on jobs early finishes sooner.
- **Constraint violations**: plans that broke a rule (two tractors on one job, wrong implement, not enough fuel, missed deadline, a job lost track of). Counted by the Safety Agent on every re-plan.

The two dispatchers we compare with never plan ahead. **FCFS** (first come, first served) is the starter rule from the brief: a free tractor takes the first job in the list it can do. **EDF** (earliest deadline first) is a stronger rule we added: a free tractor takes the job whose deadline is nearest.

## Read this before quoting the numbers

- **Three of the four families lean our way by construction.** The Calm, Some trouble and Rough day shifts are adjusted so that the coordinator's own opening plan can finish every job. The Benchmark family is not adjusted, so it is the fairest comparison, and it says the same thing.
- **Total driving is about level with FCFS.** We finish more jobs, so we visit more fields. The gain is in driving per job, not in total hours.
- **Our shift is longer.** We keep working on jobs that FCFS has already given up on.
- **We do lose some shifts.** A breakdown or another event can hit a plan that was the best one before it happened.
- The weather and the events are scripted by the simulator; none of this is field data.
