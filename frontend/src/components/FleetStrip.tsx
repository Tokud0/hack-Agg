import { motion } from 'framer-motion'
import type { Job, Tractor } from '../types'
import { tractorColor } from '../theme'
import { AlertIcon, BoltIcon, ChatIcon, FuelIcon, JobTypeIcon } from './Icons'

const STATUS_PILL: Record<string, { label: string; cls: string }> = {
  idle: { label: 'Idle', cls: 'bg-white/10 text-white/60' },
  traveling: { label: 'Driving', cls: 'bg-sky-400/15 text-sky-300' },
  working: { label: 'Working', cls: 'bg-leaf/15 text-leaf' },
  refueling: { label: 'Refuelling', cls: 'bg-wheat/20 text-wheat' },
  broken: { label: 'Broken down', cls: 'bg-alarm/20 text-alarm' },
}

interface FleetStripProps {
  tractors: Tractor[]
  jobs: Job[]
  onBreak: (tractorId: string) => void
  onSelectJob: (jobId: string) => void
  /** One card per row, for a narrow side column. */
  isStacked?: boolean
  /** Latest thing each tractor's agent said, by tractor id. */
  lastWords?: Record<string, string>
}

function TractorCard({ t, jobs, said, onBreak, onSelectJob }: { t: Tractor; jobs: Map<string, Job>; said?: string } & Pick<FleetStripProps, 'onBreak' | 'onSelectJob'>) {
  const color = t.status === 'broken' ? '#ff5d5d' : tractorColor(t.id)
  const fuelShare = Math.max(0, Math.min(1, t.fuel / t.fuel_capacity))
  const current = t.current_job ? jobs.get(t.current_job) : undefined
  const pill = STATUS_PILL[t.status]
  return (
    <motion.div layout className={`relative overflow-hidden rounded-xl border p-3 ${t.status === 'broken' ? 'border-alarm/50 bg-alarm/5' : 'border-white/8 bg-black/20'}`}>
      <div className="absolute inset-y-0 left-0 w-1" style={{ background: color }} />
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg font-extrabold" style={{ color }}>{t.id}</span>
          <span className="flex items-center gap-1 text-[11px] text-white/50"><JobTypeIcon type={t.implement === 'mower' ? 'mow' : 'spray'} size={12} />{t.implement}</span>
        </div>
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${pill.cls}`}>
          {t.status === 'broken' && <AlertIcon size={10} className="mr-1 inline" />}{pill.label}
        </span>
      </div>

      <div className="mt-2 flex items-center gap-2 text-[11px] text-white/55">
        <FuelIcon size={12} />
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
          <motion.div className="h-full rounded-full" animate={{ width: `${fuelShare * 100}%` }}
            style={{ background: fuelShare < 0.2 ? '#ff5d5d' : fuelShare < 0.45 ? '#f2c46d' : '#7bd88f' }} />
        </div>
        <span className="w-14 text-right font-mono">{Math.round(t.fuel)}/{t.fuel_capacity}</span>
        {t.refuels > 0 && <span className="rounded bg-wheat/15 px-1 text-[10px] text-wheat">{t.refuels} refuel{t.refuels > 1 ? 's' : ''}</span>}
      </div>

      <div className="mt-2 min-h-[34px] text-[11.5px]">
        {current ? (
          <button type="button" className="w-full text-left" onClick={() => onSelectJob(current.id)}>
            <div className="flex justify-between"><span className="text-white/80">{t.refuel_stop ? 'Refuel, then ' : 'Now: '}<b>{current.id}</b> on {current.field_id}</span><span className="font-mono text-white/50">{Math.round(current.progress * 100)}%</span></div>
            <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/10">
              <motion.div className="h-full rounded-full" style={{ background: color }} animate={{ width: `${current.progress * 100}%` }} />
            </div>
          </button>
        ) : (
          <span className="text-white/35">{t.status === 'broken' ? 'Out of service. Its work was handed over.' : 'No current job'}</span>
        )}
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1">
        <span className="text-[10px] uppercase tracking-wider text-white/35">Next</span>
        {t.queue.length === 0 && <span className="text-[11px] text-white/30">—</span>}
        {t.queue.map((jid) => (
          <motion.button type="button" layout key={jid} onClick={() => onSelectJob(jid)}
            className="rounded border px-1.5 font-mono text-[10.5px] hover:bg-white/10" style={{ borderColor: `${color}66`, color }}>
            {jid}
          </motion.button>
        ))}
      </div>

      {said && (
        <p className="mt-2 flex gap-1.5 rounded-md bg-white/5 px-2 py-1.5 text-[11px] leading-snug text-white/65" title={`${t.id}'s agent, last planning round`}>
          <ChatIcon size={12} className="mt-0.5 shrink-0" style={{ color }} />{said}
        </p>
      )}

      {t.status !== 'broken' && (
        <button type="button" onClick={() => onBreak(t.id)}
          className="mt-2 flex w-full items-center justify-center gap-1 rounded-md border border-alarm/30 py-1 text-[11px] font-semibold text-alarm/80 hover:bg-alarm/15 hover:text-alarm">
          <BoltIcon size={12} />Simulate breakdown
        </button>
      )}
    </motion.div>
  )
}

export function FleetStrip({ tractors, jobs, onBreak, onSelectJob, isStacked = false, lastWords }: FleetStripProps) {
  const byId = new Map(jobs.map((j) => [j.id, j]))
  return (
    <div className={`grid grid-cols-1 gap-3 ${isStacked ? '' : 'md:grid-cols-3'}`}>
      {tractors.map((t) => <TractorCard key={t.id} t={t} jobs={byId} said={lastWords?.[t.id]} onBreak={onBreak} onSelectJob={onSelectJob} />)}
    </div>
  )
}
