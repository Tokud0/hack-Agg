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
  const [isRiskOnly, setIsRiskOnly] = useState(false)
  const run = runs[strategy]
  const riskCount = run.jobs.filter((j) => j.at_risk).length
  const jobs = isRiskOnly ? run.jobs.filter((j) => j.at_risk) : run.jobs
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
        <div className="mb-1 flex items-center justify-between gap-2">
          <h2 className="text-xs font-bold uppercase tracking-widest text-white/60">{isRiskOnly ? 'Jobs at risk' : 'All jobs'}</h2>
          <button type="button" aria-pressed={isRiskOnly} onClick={() => setIsRiskOnly((on) => !on)}
            className={`rounded-md border px-2 py-0.5 text-[11.5px] font-semibold ${isRiskOnly ? 'border-wheat bg-wheat/20 text-wheat' : riskCount ? 'border-wheat/50 text-wheat hover:bg-wheat/10' : 'border-white/10 text-white/45'}`}>
            At risk: {riskCount}
          </button>
        </div>
        <div className="min-h-0 flex-1">
          {isRiskOnly && jobs.length === 0
            ? <p className="py-6 text-center text-sm text-white/40">No job is close to its deadline. A job is at risk when the plan finishes it less than 30 minutes before it is due.</p>
            : <JobTable jobs={jobs} highlight={highlight} onSelectJob={onSelectJob} />}
        </div>
      </section>
    </div>
  )
}
