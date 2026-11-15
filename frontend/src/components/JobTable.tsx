import type { Job } from '../types'
import { JOB_ICON, PRIORITY_STYLE, clock, tractorColor } from '../theme'

const STATUS_STYLE: Record<string, string> = {
  pending: 'text-white/50',
  assigned: 'text-white/80',
  in_progress: 'text-wheat',
  done: 'text-leaf',
  unassignable: 'text-alarm',
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
          <tr><th className="py-1">Job</th><th>Field</th><th>Prio</th><th>Due</th><th>Tractor</th><th className="w-24">Progress</th><th>Status</th></tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id} onClick={() => onSelectJob(j.id)}
              className={`cursor-pointer border-b border-white/5 hover:bg-white/5 ${highlight?.has(j.id) ? 'bg-wheat/10' : ''}`}>
              <td className="py-1 font-mono font-bold">{JOB_ICON[j.type]} {j.id}</td>
              <td>{j.field_id}</td>
              <td><span className={`rounded border px-1 text-[10px] font-bold ${PRIORITY_STYLE[j.priority]}`}>P{j.priority}</span></td>
              <td className="font-mono text-white/60">{clock(j.deadline)}</td>
              <td>{j.tractor_id ? <span className="font-bold" style={{ color: tractorColor(j.tractor_id) }}>{j.tractor_id}</span> : '—'}</td>
              <td>
                <div className="h-1.5 rounded-full bg-white/10">
                  <div className="h-full rounded-full bg-leaf transition-[width] duration-300" style={{ width: `${j.progress * 100}%` }} />
                </div>
              </td>
              <td className={STATUS_STYLE[j.status]} title={j.reason ?? undefined}>
                {j.status.replace('_', ' ')}{j.status === 'unassignable' && ' ⓘ'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
