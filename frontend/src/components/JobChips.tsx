import type { Job } from '../types'
import { clock, tractorColor } from '../theme'

type Outcome = 'done' | 'late' | 'active' | 'waiting' | 'lost'

const DEADLINE_TOLERANCE_H = 1e-6

function outcomeOf(job: Job): Outcome {
  if (job.status === 'done') return job.completed_at !== null && job.completed_at > job.deadline + DEADLINE_TOLERANCE_H ? 'late' : 'done'
  if (job.status === 'unassignable') return 'lost'
  return job.status === 'in_progress' ? 'active' : 'waiting'
}

const STYLE: Record<Outcome, string> = {
  done: 'border-leaf bg-leaf text-black',
  late: 'border-wheat/60 bg-wheat/20 text-wheat',
  active: 'bg-transparent text-white',
  waiting: 'border-white/15 bg-transparent text-white/45',
  lost: 'border-alarm/60 bg-alarm/15 text-alarm line-through',
}

const WORD: Record<Outcome, string> = {
  done: 'done on time', late: 'done after its deadline', active: 'in progress', waiting: 'waiting', lost: 'not done',
}

interface JobChipsProps {
  jobs: Job[]
  /** The same jobs in the run this one is compared with; jobs that ended differently get a ring. */
  compareTo?: Job[]
  onSelectJob: (jobId: string) => void
}

/** Every job as one chip, so "7 of 10 done" can be counted at a glance and compared side by side. */
export function JobChips({ jobs, compareTo, onSelectJob }: JobChipsProps) {
  const other = new Map((compareTo ?? []).map((j) => [j.id, outcomeOf(j)]))
  return (
    <ul className="flex flex-wrap gap-1" aria-label="Jobs">
      {jobs.map((job) => {
        const outcome = outcomeOf(job)
        const theirs = other.get(job.id)
        // Only a settled difference counts: done here and lost there, or the reverse.
        const isDecisive = (outcome === 'done' && theirs === 'lost') || (outcome === 'lost' && theirs === 'done')
        const detail = job.reason && outcome === 'lost' ? `: ${job.reason}` : ''
        return (
          <li key={job.id}>
            <button type="button" onClick={() => onSelectJob(job.id)}
              title={`${job.id}, P${job.priority}, due ${clock(job.deadline)}: ${WORD[outcome]}${detail}${job.at_risk && outcome !== 'done' && outcome !== 'lost' ? ', finishing close to its deadline' : ''}`}
              className={`relative rounded-md border px-1.5 py-0.5 font-mono text-[10.5px] font-bold ${STYLE[outcome]} ${isDecisive ? 'ring-2 ring-wheat ring-offset-1 ring-offset-soil-900' : ''}`}
              style={outcome === 'active' ? { borderColor: tractorColor(job.tractor_id) } : undefined}>
              {job.at_risk && outcome !== 'done' && outcome !== 'lost' && <span className="absolute -bottom-1 -right-1 h-2 w-2 rounded-full bg-wheat ring-1 ring-soil-900" aria-label="at risk" />}
              {job.priority === 1 && <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-alarm ring-1 ring-soil-900" aria-label="urgent" />}
              {job.id}
              {outcome === 'active' && <span className="ml-1 font-normal text-white/55">{Math.round(job.progress * 100)}%</span>}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export function JobChipsLegend({ hasComparison = false }: { hasComparison?: boolean }) {
  const chip = 'rounded border px-1 font-mono text-[9.5px] font-bold'
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-white/50">
      <span className="flex items-center gap-1"><span className={`${chip} ${STYLE.done}`}>J</span>done on time</span>
      <span className="flex items-center gap-1"><span className={`${chip} border-white/50 text-white`}>J</span>in progress</span>
      <span className="flex items-center gap-1"><span className={`${chip} ${STYLE.waiting}`}>J</span>waiting</span>
      <span className="flex items-center gap-1"><span className={`${chip} ${STYLE.lost}`}>J</span>not done</span>
      <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-alarm" />urgent (P1)</span>
      <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-wheat" />close to its deadline</span>
      {hasComparison && <span className="flex items-center gap-1"><span className={`${chip} ${STYLE.waiting} ring-2 ring-wheat`}>J</span>ended differently on the other side</span>}
    </div>
  )
}
