import { motion } from 'framer-motion'
import type { GanttBlock, RunSnapshot } from '../types'
import { clock, tractorColor } from '../theme'
import { JobTypeIcon } from './Icons'

const WIDTH = 1000
const LABEL_W = 70
const LANE_H = 46
const TOP = 22
const BLOCK_PAD = 7
const MIN_HORIZON = 10

interface GanttProps {
  run: RunSnapshot
  highlight?: Set<string>
  onSelectJob?: (jobId: string) => void
}

function blockKey(b: GanttBlock): string {
  // Planned/active blocks keep their key across re-plans so they glide between lanes.
  return b.kind === 'planned' || b.kind === 'active' ? `live-${b.job_id}` : `${b.kind}-${b.job_id}-${b.start}`
}

export function Gantt({ run, highlight, onSelectJob }: GanttProps) {
  const lanes = run.tractors.map((t) => t.id)
  const laneIndex = new Map(lanes.map((id, i) => [id, i]))
  const jobs = new Map(run.jobs.map((j) => [j.id, j]))
  const horizon = Math.max(MIN_HORIZON, ...run.gantt.map((b) => b.end), ...run.jobs.map((j) => j.deadline)) + 0.5
  const x = (h: number) => LABEL_W + (h / horizon) * (WIDTH - LABEL_W - 10)
  const height = TOP + lanes.length * LANE_H + 6

  return (
    <svg viewBox={`0 0 ${WIDTH} ${height}`} className="w-full">
      {Array.from({ length: Math.floor(horizon) + 1 }, (_, h) => (
        <g key={h}>
          <line x1={x(h)} y1={TOP - 4} x2={x(h)} y2={height} stroke="#ffffff0d" />
          <text x={x(h)} y={13} fontSize={10} fill="#7d8f83" textAnchor="middle" fontFamily="JetBrains Mono">{clock(h)}</text>
        </g>
      ))}

      {run.tractors.map((t, i) => {
        const y = TOP + i * LANE_H
        const broken = t.status === 'broken'
        return (
          <g key={t.id}>
            <rect x={0} y={y} width={WIDTH} height={LANE_H} fill={broken ? '#ff5d5d10' : i % 2 ? '#ffffff04' : 'transparent'} />
            <circle cx={14} cy={y + LANE_H / 2} r={6} fill={broken ? '#ff5d5d' : tractorColor(t.id)} />
            <text x={26} y={y + LANE_H / 2 + 4} fontSize={13} fontWeight={700} fill="#e6efe8">{t.id}</text>
            <text x={26} y={y + LANE_H / 2 + 16} fontSize={8} fill="#7d8f83">{t.implement}</text>
            {broken && (
              <text x={WIDTH - 14} y={y + LANE_H / 2 + 4} fontSize={11} fill="#ff5d5d" textAnchor="end" fontWeight={700}>
                BROKEN DOWN
              </text>
            )}
          </g>
        )
      })}

      {run.gantt.map((b) => {
        const lane = laneIndex.get(b.tractor_id) ?? 0
        const job = jobs.get(b.job_id)
        const color = tractorColor(b.tractor_id)
        const w = Math.max(4, x(b.end) - x(b.start))
        const y = TOP + lane * LANE_H + BLOCK_PAD
        const h = LANE_H - BLOCK_PAD * 2
        const isHighlighted = highlight?.has(b.job_id)
        const fill = b.kind === 'planned' ? `${color}33` : b.kind === 'interrupted' ? '#ff5d5d55' : color
        return (
          <motion.g key={blockKey(b)} className="cursor-pointer" onClick={() => onSelectJob?.(b.job_id)}
            initial={{ opacity: 0 }} animate={{ opacity: 1, x: x(b.start), y }}
            transition={{ type: 'spring', stiffness: 120, damping: 18 }}>
            <motion.rect width={w} height={h} rx={6} fill={fill}
              stroke={isHighlighted ? '#f2c46d' : b.kind === 'planned' ? color : 'transparent'}
              strokeWidth={isHighlighted ? 2.5 : 1.2} strokeDasharray={b.kind === 'planned' ? '4 3' : undefined}
              animate={{ width: w }} transition={{ type: 'spring', stiffness: 120, damping: 18 }} />
            {b.kind === 'interrupted' && <line x1={w} y1={-2} x2={w} y2={h + 2} stroke="#ff5d5d" strokeWidth={2.5} />}
            {w > 34 && (
              <g color={b.kind === 'done' || b.kind === 'active' ? '#0a100c' : '#e6efe8'}>
                {job && <JobTypeIcon type={job.type} size={12} x={6} y={h / 2 - 6} />}
                <text x={21} y={h / 2 + 4} fontSize={11} fontWeight={700} fill="currentColor">{b.job_id}</text>
              </g>
            )}
          </motion.g>
        )
      })}

      {run.jobs.filter((j) => j.status === 'assigned' || j.status === 'in_progress').map((j) => {
        const lane = laneIndex.get(j.tractor_id ?? '')
        if (lane === undefined) return null
        const y = TOP + lane * LANE_H
        return (
          <g key={`dl-${j.id}`} opacity={0.75}>
            <line x1={x(j.deadline)} y1={y + 3} x2={x(j.deadline)} y2={y + LANE_H - 3} stroke="#ff5d5d" strokeWidth={1.5} strokeDasharray="2 2" />
            <text x={x(j.deadline) + 2} y={y + 10} fontSize={8} fill="#ff8a8a">{j.id}</text>
          </g>
        )
      })}

      {run.log.filter((e) => e.kind === 'event').map((e) => (
        <g key={`ev-${e.index}`}>
          <line x1={x(e.time)} y1={TOP - 4} x2={x(e.time)} y2={height} stroke="#ff5d5d" strokeWidth={1.5} />
          <rect x={x(e.time) - 3} y={TOP - 8} width={6} height={6} fill="#ff5d5d" transform={`rotate(45 ${x(e.time)} ${TOP - 5})`} />
        </g>
      ))}

      <motion.line y1={TOP - 6} y2={height} stroke="#7bd88f" strokeWidth={2}
        animate={{ x1: x(run.time), x2: x(run.time) }} transition={{ duration: 0.12, ease: 'linear' }} />
      <motion.text y={TOP - 8} fontSize={9} fill="#7bd88f" textAnchor="middle" fontWeight={700}
        animate={{ x: x(run.time) }} transition={{ duration: 0.12, ease: 'linear' }}>NOW</motion.text>
    </svg>
  )
}

export function GanttLegend() {
  const swatch = 'inline-block h-2.5 w-4 rounded-sm'
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10.5px] text-white/50">
      <span className="flex items-center gap-1.5"><span className={swatch} style={{ background: '#c792ea' }} />done / working</span>
      <span className="flex items-center gap-1.5"><span className={`${swatch} border border-dashed border-[#c792ea]`} style={{ background: '#c792ea33' }} />planned</span>
      <span className="flex items-center gap-1.5"><span className={swatch} style={{ background: '#ff5d5d55', borderRight: '2px solid #ff5d5d' }} />interrupted</span>
      <span className="flex items-center gap-1.5"><span className="inline-block h-3 border-l-2 border-dashed border-alarm" />deadline</span>
      <span className="flex items-center gap-1.5"><span className="inline-block h-2 w-2 rotate-45 bg-alarm" />event</span>
      <span className="flex items-center gap-1.5"><span className="inline-block h-3 border-l-2 border-leaf" />now</span>
    </div>
  )
}
