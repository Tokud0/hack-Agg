import { useState } from 'react'
import { Gantt, GanttLegend } from '../components/Gantt'
import { JobTable } from '../components/JobTable'
import { Segmented, ViewHeader } from '../components/shell/ViewHeader'
import { STRATEGY_OPTIONS } from '../strategies'
import type { RunSnapshot, Strategy } from '../types'

interface ScheduleViewProps {
  runs: Record<Strategy, RunSnapshot>
  highlight: Set<string>
  onSelectJob: (jobId: string) => void
}

export function ScheduleView({ runs, highlight, onSelectJob }: ScheduleViewProps) {
  const [strategy, setStrategy] = useState<Strategy>('coordinator')
  const run = runs[strategy]
  return (
    <div className="flex h-full flex-col gap-3">
      <ViewHeader title="Schedule" description='Who does what and when. Click a block or a row to ask "why?"'
        actions={<Segmented label="Schedule of" options={STRATEGY_OPTIONS} value={strategy} onChange={setStrategy} />} />
      <section className="panel p-3" aria-label="Timeline">
        <h2 className="mb-1 text-xs font-bold uppercase tracking-widest text-white/60">Timeline by tractor</h2>
        <Gantt run={run} highlight={highlight} onSelectJob={onSelectJob} />
        <div className="mt-1"><GanttLegend /></div>
      </section>
      <section className="panel flex min-h-[260px] flex-1 flex-col p-3" aria-label="Jobs">
        <h2 className="mb-1 text-xs font-bold uppercase tracking-widest text-white/60">All jobs</h2>
        <div className="min-h-0 flex-1"><JobTable jobs={run.jobs} highlight={highlight} onSelectJob={onSelectJob} /></div>
      </section>
    </div>
  )
}
