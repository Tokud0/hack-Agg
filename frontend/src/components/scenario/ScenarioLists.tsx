import type { ReactNode } from 'react'
import { MAX_JOBS, MAX_TRACTORS, type Implement, type JobType, type Scenario, type ScenarioJob, type ScenarioTractor } from '../../scenario'
import { clock, tractorColor } from '../../theme'
import { CloseIcon, PlusIcon } from '../Icons'
import { inputCls } from '../tools/shared'

const TANKS = [60, 80, 100, 150]
const WORK_HOURS = [0.5, 1, 1.5, 2, 2.5, 3]
const SHIFT_HOURS = 12
/** Deadlines every half hour through the shift, as hours after the start. */
const DEADLINES = Array.from({ length: SHIFT_HOURS * 2 - 1 }, (_, i) => 1 + i * 0.5)

const heading = 'text-xs font-bold uppercase tracking-widest text-white/60'
const selectCls = `${inputCls} px-1.5 py-1`

/** The standard options plus the current value when it is not one of them (a generated or uploaded scenario). */
const withValue = (options: number[], value: number): number[] =>
  options.includes(value) ? options : [...options, value].sort((a, b) => a - b)

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" aria-label={label} onClick={onClick} className="rounded p-1 text-white/35 hover:bg-alarm/15 hover:text-alarm"><CloseIcon size={13} /></button>
  )
}

function AddButton({ children, disabled, onClick }: { children: ReactNode; disabled: boolean; onClick: () => void }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick}
      className="flex items-center gap-1 rounded-md border border-leaf/40 px-2 py-1 text-[11.5px] font-semibold text-leaf hover:bg-leaf/10 disabled:opacity-35"><PlusIcon size={12} />{children}</button>
  )
}

interface TractorListProps {
  tractors: ScenarioTractor[]
  onAdd: () => void
  onUpdate: (id: string, patch: Partial<ScenarioTractor>) => void
  onRemove: (id: string) => void
}

export function TractorList({ tractors, onAdd, onUpdate, onRemove }: TractorListProps) {
  return (
    <section aria-label="Tractors">
      <div className="flex items-center justify-between">
        <h2 className={heading}>Tractors <span className="font-mono text-white/35">{tractors.length}/{MAX_TRACTORS}</span></h2>
        <AddButton disabled={tractors.length >= MAX_TRACTORS} onClick={onAdd}>Add tractor</AddButton>
      </div>
      <ul className="mt-1.5 space-y-1">
        {tractors.map((t) => (
          <li key={t.id} className="flex items-center gap-2 rounded-lg bg-black/20 px-2 py-1.5">
            <b className="w-7 text-sm" style={{ color: tractorColor(t.id) }}>{t.id}</b>
            <select aria-label={`${t.id} implement`} className={selectCls} value={t.implement} onChange={(e) => onUpdate(t.id, { implement: e.target.value as Implement })}>
              <option value="sprayer">sprayer</option>
              <option value="mower">mower</option>
            </select>
            <span className="text-[11px] text-white/45">tank</span>
            <select aria-label={`${t.id} tank size`} className={selectCls} value={t.fuel_capacity} onChange={(e) => onUpdate(t.id, { fuel_capacity: Number(e.target.value) })}>
              {withValue(TANKS, t.fuel_capacity).map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            <span className="ml-auto"><RemoveButton label={`Remove ${t.id}`} onClick={() => onRemove(t.id)} /></span>
          </li>
        ))}
        {tractors.length === 0 && <li className="text-[12px] text-white/40">No tractors yet.</li>}
      </ul>
    </section>
  )
}

interface JobListProps {
  scenario: Scenario
  selectedField: string | null
  onAdd: (fieldId: string) => void
  onUpdate: (id: string, patch: Partial<ScenarioJob>) => void
  onRemove: (id: string) => void
}

export function JobList({ scenario, selectedField, onAdd, onUpdate, onRemove }: JobListProps) {
  const { jobs, fields } = scenario
  const target = selectedField ?? fields[0]?.id
  return (
    <section aria-label="Jobs">
      <div className="flex items-center justify-between">
        <h2 className={heading}>Jobs <span className="font-mono text-white/35">{jobs.length}/{MAX_JOBS}</span></h2>
        <AddButton disabled={!target || jobs.length >= MAX_JOBS} onClick={() => target && onAdd(target)}>{target ? `Add job on ${target}` : 'Place a field first'}</AddButton>
      </div>
      <ul className="mt-1.5 space-y-1">
        {jobs.map((j) => (
          <li key={j.id} className={`flex flex-wrap items-center gap-1.5 rounded-lg px-2 py-1.5 ${j.field_id === selectedField ? 'bg-leaf/10' : 'bg-black/20'}`}>
            <b className="w-7 font-mono text-[12px]">{j.id}</b>
            <select aria-label={`${j.id} type`} className={selectCls} value={j.type} onChange={(e) => onUpdate(j.id, { type: e.target.value as JobType })}>
              <option value="spray">spray</option>
              <option value="mow">mow</option>
            </select>
            <select aria-label={`${j.id} field`} className={selectCls} value={j.field_id} onChange={(e) => onUpdate(j.id, { field_id: e.target.value })}>
              {fields.map((f) => <option key={f.id}>{f.id}</option>)}
            </select>
            <select aria-label={`${j.id} priority`} className={selectCls} value={j.priority} onChange={(e) => onUpdate(j.id, { priority: Number(e.target.value) })}>
              <option value={1}>P1</option>
              <option value={2}>P2</option>
              <option value={3}>P3</option>
            </select>
            <span className="text-[11px] text-white/45">by</span>
            <select aria-label={`${j.id} deadline`} className={selectCls} value={j.deadline} onChange={(e) => onUpdate(j.id, { deadline: Number(e.target.value) })}>
              {withValue(DEADLINES, j.deadline).map((h) => <option key={h} value={h}>{clock(h)}</option>)}
            </select>
            <select aria-label={`${j.id} work hours`} className={selectCls} value={j.work_hours} onChange={(e) => onUpdate(j.id, { work_hours: Number(e.target.value) })}>
              {withValue(WORK_HOURS, j.work_hours).map((h) => <option key={h} value={h}>{h} h</option>)}
            </select>
            <span className="ml-auto"><RemoveButton label={`Remove ${j.id}`} onClick={() => onRemove(j.id)} /></span>
          </li>
        ))}
        {jobs.length === 0 && <li className="text-[12px] text-white/40">No jobs yet. Select a field on the map, then add a job on it.</li>}
      </ul>
    </section>
  )
}
