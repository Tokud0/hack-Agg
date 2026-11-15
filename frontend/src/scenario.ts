/** The scenario file format of the backend, plus pure helpers for editing one. Every helper returns a new scenario. */

export type Implement = 'sprayer' | 'mower'
export type JobType = 'spray' | 'mow'

export interface ScenarioTractor {
  id: string
  implement: Implement
  fuel_capacity: number
  speed: number
  fuel_per_travel_hour: number
  fuel_per_work_hour: number
}

export interface ScenarioField {
  id: string
  x: number
  y: number
}

export interface ScenarioJob {
  id: string
  type: JobType
  field_id: string
  priority: number
  deadline: number
  work_hours: number
}

export interface Scenario {
  name: string
  shift_start_hour: number
  refuel_hours: number | null
  depot: { id: string; x: number; y: number }
  tractors: ScenarioTractor[]
  fields: ScenarioField[]
  jobs: ScenarioJob[]
}

export const GRID = 10
export const MAX_TRACTORS = 4
export const MAX_FIELDS = 10
export const MAX_JOBS = 14
const DEFAULT_TANK = 100
const DEFAULT_DEADLINE_H = 8
const DEFAULT_WORK_H = 1

export const IMPLEMENT_FOR: Record<JobType, Implement> = { spray: 'sprayer', mow: 'mower' }
const JOB_FOR: Record<Implement, JobType> = { sprayer: 'spray', mower: 'mow' }

export const EMPTY_SCENARIO: Scenario = {
  name: 'My shift',
  shift_start_hour: 6,
  refuel_hours: 0.25,
  depot: { id: 'D', x: 5, y: 0 },
  tractors: [],
  fields: [],
  jobs: [],
}

/** Lowest unused id with this prefix: T1, T2, ... or J01, J02, ... */
function nextId(prefix: string, taken: string[], pad = 1): string {
  for (let n = 1; ; n += 1) {
    const id = `${prefix}${String(n).padStart(pad, '0')}`
    if (!taken.includes(id)) return id
  }
}

export function isFree(s: Scenario, x: number, y: number, exceptField?: string): boolean {
  if (x < 0 || x > GRID || y < 1 || y > GRID) return false
  return !s.fields.some((f) => f.id !== exceptField && f.x === x && f.y === y)
}

export function withField(s: Scenario, x: number, y: number): Scenario {
  if (s.fields.length >= MAX_FIELDS || !isFree(s, x, y)) return s
  return { ...s, fields: [...s.fields, { id: nextId('F', s.fields.map((f) => f.id)), x, y }] }
}

export function movedField(s: Scenario, id: string, x: number, y: number): Scenario {
  if (!isFree(s, x, y, id)) return s
  return { ...s, fields: s.fields.map((f) => (f.id === id ? { ...f, x, y } : f)) }
}

/** Removing a field removes the jobs on it. */
export function withoutField(s: Scenario, id: string): Scenario {
  return { ...s, fields: s.fields.filter((f) => f.id !== id), jobs: s.jobs.filter((j) => j.field_id !== id) }
}

export function withTractor(s: Scenario): Scenario {
  if (s.tractors.length >= MAX_TRACTORS) return s
  const hasSprayer = s.tractors.some((t) => t.implement === 'sprayer')
  const tractor: ScenarioTractor = {
    id: nextId('T', s.tractors.map((t) => t.id)), implement: hasSprayer ? 'mower' : 'sprayer',
    fuel_capacity: DEFAULT_TANK, speed: 4, fuel_per_travel_hour: 5, fuel_per_work_hour: 8,
  }
  return { ...s, tractors: [...s.tractors, tractor] }
}

export const updatedTractor = (s: Scenario, id: string, patch: Partial<ScenarioTractor>): Scenario =>
  ({ ...s, tractors: s.tractors.map((t) => (t.id === id ? { ...t, ...patch } : t)) })

export const withoutTractor = (s: Scenario, id: string): Scenario => ({ ...s, tractors: s.tractors.filter((t) => t.id !== id) })

export function withJob(s: Scenario, fieldId: string): Scenario {
  if (s.jobs.length >= MAX_JOBS || !s.fields.some((f) => f.id === fieldId)) return s
  const type = JOB_FOR[s.tractors[0]?.implement ?? 'sprayer']
  const job: ScenarioJob = {
    id: nextId('J', s.jobs.map((j) => j.id), 2), type, field_id: fieldId, priority: 2, deadline: DEFAULT_DEADLINE_H, work_hours: DEFAULT_WORK_H,
  }
  return { ...s, jobs: [...s.jobs, job] }
}

export const updatedJob = (s: Scenario, id: string, patch: Partial<ScenarioJob>): Scenario =>
  ({ ...s, jobs: s.jobs.map((j) => (j.id === id ? { ...j, ...patch } : j)) })

export const withoutJob = (s: Scenario, id: string): Scenario => ({ ...s, jobs: s.jobs.filter((j) => j.id !== id) })

export interface ScenarioCheck {
  /** Reasons the shift cannot start. */
  blockers: string[]
  /** Things that will work but probably are not what the operator meant. */
  warnings: string[]
}

export function checkScenario(s: Scenario): ScenarioCheck {
  const blockers = [
    ...(s.tractors.length ? [] : ['Add at least one tractor.']),
    ...(s.fields.length ? [] : ['Click the map to place at least one field.']),
    ...(s.jobs.length ? [] : ['Add at least one job.']),
  ]
  const implementsOwned = new Set(s.tractors.map((t) => t.implement))
  const warnings = s.jobs
    .filter((j) => !implementsOwned.has(IMPLEMENT_FOR[j.type]))
    .map((j) => `${j.id} needs a ${IMPLEMENT_FOR[j.type]}, and no tractor has one.`)
  return { blockers, warnings }
}
