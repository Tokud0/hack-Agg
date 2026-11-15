import type { Strategy } from './types'

export type BaselineKind = 'baseline' | 'edf'

export const BASELINES: Record<BaselineKind, { short: string; label: string; subtitle: string }> = {
  baseline: { short: 'FCFS', label: 'first come, first served', subtitle: 'takes jobs in list order · no planning' },
  edf: { short: 'EDF', label: 'earliest deadline first', subtitle: 'takes the most urgent deadline · no planning' },
}

export const BASELINE_OPTIONS = (Object.keys(BASELINES) as BaselineKind[]).map((id) => ({ id, label: BASELINES[id].short }))

export const STRATEGY_OPTIONS: { id: Strategy; label: string }[] = [
  { id: 'coordinator', label: 'Our coordinator' },
  { id: 'baseline', label: 'FCFS' },
  { id: 'edf', label: 'EDF' },
]
