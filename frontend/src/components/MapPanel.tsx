import type { ReactNode } from 'react'
import type { Speech } from '../radio'
import type { Job, MapInfo, Metrics, RunSnapshot } from '../types'
import { FieldMap, type Handoff } from './FieldMap'
import { JobChips } from './JobChips'
import { Counters } from './Panels'

interface MapPanelProps {
  run: RunSnapshot
  map: MapInfo
  title: ReactNode
  subtitle: string
  accent: string
  highlight: Set<string>
  handoffs: Handoff[]
  compareTo?: Metrics
  onSelectJob: (id: string) => void
  speech?: Speech | null
  /** The other run's jobs, to mark the ones that ended differently. */
  compareJobs?: Job[]
}

export function MapPanel({ run, map, title, subtitle, accent, highlight, handoffs, compareTo, onSelectJob, speech, compareJobs }: MapPanelProps) {
  return (
    <section className="panel flex h-full min-h-[460px] flex-col p-3" style={{ boxShadow: `0 0 0 1px ${accent}22, 0 10px 40px -20px ${accent}66` }}>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-extrabold uppercase tracking-widest" style={{ color: accent }}>{title}</h2>
        <span className="text-[11px] text-white/45">{subtitle}</span>
      </div>
      <Counters metrics={run.metrics} accent={accent} compareTo={compareTo} isCompact />
      <div className="mt-2"><JobChips jobs={run.jobs} compareTo={compareJobs} onSelectJob={onSelectJob} /></div>
      <div className="mt-2 min-h-0 flex-1">
        <FieldMap run={run} map={map} highlight={highlight} handoffs={handoffs} onSelectJob={onSelectJob} speech={speech} />
      </div>
    </section>
  )
}
