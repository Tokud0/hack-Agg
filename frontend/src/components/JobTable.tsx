import type { Job } from '../types'
import { PRIORITY_STYLE, clock, tractorColor } from '../theme'
import { JobTypeIcon } from './Icons'

const STATUS_STYLE: Record<string, string> = {
  pending: 'text-white/50',
  assigned: 'text-white/80',
  in_progress: 'text-wheat',
  done: 'text-leaf',
  unassignable: 'text-alarm',
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'waiting',
  assigned: 'planned',
  in_progress: 'in progress',
  done: 'done',
  unassignable: 'cannot be done',
}

const MINUTES = 60

/** Spare time before the deadline, as a person would say it. */
function spareTime(hours: number): string {
  const minutes = Math.max(0, Math.round(hours * MINUTES))
  return minutes < MINUTES ? `${minutes} min` : `${Math.floor(minutes / MINUTES)} h ${String(minutes % MINUTES).padStart(2, '0')}`
}

interface JobTableProps {
  jobs: Job[]
  highlight?: Set<string>
  onSelectJob: (jobId: string) => void
}

export function JobTable({ jobs, highlight, onSelectJob }: JobTableProps) {
  return (
    <div className="h-full overflow-y-auto">
      <table className="w-full text-[12px]">
        <thead className="sticky top-0 bg-soil-800 text-left text-[10px] uppercase tracking-wider text-white/40">
          <tr><th className="py-1">Job</th><th>Field</th><th>Prio</th><th>Due</th><th>Tractor</th><th>Finishes</th><th>Spare time</th><th className="w-24">Progress</th><th>Status</th></tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id} onClick={() => onSelectJob(j.id)}
              className={`cursor-pointer border-b border-white/5 hover:bg-white/5 ${highlight?.has(j.id) ? 'bg-wheat/10' : ''}`}>
              <td className="py-1 font-mono font-bold"><span className="inline-flex items-center gap-1.5"><JobTypeIcon type={j.type} size={12} className="text-white/50" />{j.id}</span></td>
              <td>{j.field_id}</td>
              <td><span className={`rounded border px-1 text-[10px] font-bold ${PRIORITY_STYLE[j.priority]}`}>P{j.priority}</span></td>
              <td className="font-mono text-white/60">{clock(j.deadline)}</td>
              <td>{j.tractor_id ? <span className="font-bold" style={{ color: tractorColor(j.tractor_id) }}>{j.tractor_id}</span> : '—'}</td>
              <td className="font-mono text-white/60">{j.projected_finish === null ? '—' : clock(j.projected_finish)}</td>
              <td>{j.slack === null ? <span className="text-white/30">—</span> : (
                <span className={`rounded px-1 font-mono text-[11px] ${j.at_risk ? 'bg-wheat/20 font-bold text-wheat' : 'text-white/60'}`}>
                  {spareTime(j.slack)}{j.at_risk && ' · at risk'}
                </span>
              )}</td>
              <td className="pr-4">
                <div className="h-1.5 rounded-full bg-white/10">
                  <div className="h-full rounded-full bg-leaf transition-[width] duration-300" style={{ width: `${j.progress * 100}%` }} />
                </div>
              </td>
              <td className={STATUS_STYLE[j.status]}>
                <div>{STATUS_LABEL[j.status]}</div>
                {j.reason && <div className="max-w-[260px] truncate text-[10px] text-alarm/70" title={j.reason}>{j.reason}</div>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
