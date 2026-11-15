import { AnimatePresence, motion } from 'framer-motion'
import type { Job, MapInfo, RunSnapshot, Tractor } from '../types'
import { JOB_ICON, tractorColor } from '../theme'

const GRID = 10
const FIELD_SIZE = 1.5
const TRACTOR_R = 0.36
const RING_R = 0.5
const RING_LEN = 2 * Math.PI * RING_R

export interface Handoff {
  key: string
  from: string
  to: string
  jobId: string
}

interface FieldMapProps {
  run: RunSnapshot
  map: MapInfo
  highlight?: Set<string>
  handoffs?: Handoff[]
  onSelectJob?: (jobId: string) => void
}

type Point = { x: number; y: number }
const sy = (y: number) => GRID - y

function nodePos(map: MapInfo, id: string): Point {
  if (id === map.depot.id) return { x: map.depot.x, y: map.depot.y }
  const f = map.fields.find((fl) => fl.id === id)
  return f ? { x: f.x, y: f.y } : { x: 0, y: 0 }
}

function fieldProgress(jobs: Job[]): number {
  const total = jobs.reduce((s, j) => s + j.work_hours, 0)
  return total ? jobs.reduce((s, j) => s + j.progress * j.work_hours, 0) / total : 0
}

function FieldTile({ id, x, y, jobs, highlighted, onSelect }: {
  id: string; x: number; y: number; jobs: Job[]; highlighted: boolean; onSelect?: (jobId: string) => void
}) {
  const progress = fieldProgress(jobs)
  const allDone = jobs.length > 0 && jobs.every((j) => j.status === 'done')
  const dropped = jobs.some((j) => j.status === 'unassignable')
  const active = jobs.find((j) => j.status === 'in_progress')
  const stripeColor = active ? tractorColor(active.tractor_id) : '#7bd88f'
  const half = FIELD_SIZE / 2
  const left = x - half
  const top = sy(y) - half
  return (
    <g className="cursor-pointer" onClick={() => jobs[0] && onSelect?.(jobs[0].id)}>
      {highlighted && (
        <motion.rect
          x={left - 0.18} y={top - 0.18} width={FIELD_SIZE + 0.36} height={FIELD_SIZE + 0.36} rx={0.35}
          fill="none" stroke="#f2c46d" strokeWidth={0.08}
          initial={{ opacity: 0 }} animate={{ opacity: [0.2, 1, 0.2] }} transition={{ repeat: Infinity, duration: 1.4 }}
        />
      )}
      <rect x={left} y={top} width={FIELD_SIZE} height={FIELD_SIZE} rx={0.25}
        fill={allDone ? '#254a30' : '#1b2a20'} stroke={dropped ? '#ff5d5d' : '#3a5243'}
        strokeWidth={dropped ? 0.07 : 0.04} strokeDasharray={dropped ? '0.15 0.1' : undefined} />
      <clipPath id={`clip-${id}`}>
        <rect x={left} y={top} width={FIELD_SIZE * progress} height={FIELD_SIZE} rx={0.25} />
      </clipPath>
      <rect x={left} y={top} width={FIELD_SIZE} height={FIELD_SIZE} rx={0.25}
        fill={`url(#stripes-${active ? active.tractor_id : 'done'})`} clipPath={`url(#clip-${id})`}
        style={{ color: stripeColor }} />
      <text x={left + 0.12} y={top + 0.36} fontSize={0.3} fill="#cfe0d4" fontWeight={700}>{id}</text>
      <text x={x + half - 0.12} y={top + 0.38} fontSize={0.3} textAnchor="end">
        {jobs.map((j) => JOB_ICON[j.type]).join('')}
      </text>
      <text x={x} y={sy(y) + half - 0.15} fontSize={0.24} fill="#9fb3a5" textAnchor="middle" fontFamily="JetBrains Mono">
        {jobs.map((j) => j.id).join(' ')}
      </text>
    </g>
  )
}

function TractorMarker({ t }: { t: Tractor }) {
  const color = t.status === 'broken' ? '#ff5d5d' : tractorColor(t.id)
  const fuelShare = Math.max(0, Math.min(1, t.fuel / t.fuel_capacity))
  const fuelColor = fuelShare < 0.2 ? '#ff5d5d' : fuelShare < 0.45 ? '#f2c46d' : '#7bd88f'
  return (
    <g style={{ transform: `translate(${t.x}px, ${sy(t.y)}px)`, transition: 'transform 140ms linear' }}>
      {t.status === 'broken' && <circle className="pulse-ring" r={0.5} fill="none" stroke="#ff5d5d" strokeWidth={0.08} />}
      <circle r={RING_R} fill="none" stroke="#ffffff14" strokeWidth={0.09} />
      <circle r={RING_R} fill="none" stroke={fuelColor} strokeWidth={0.09}
        strokeDasharray={`${RING_LEN * fuelShare} ${RING_LEN}`} transform="rotate(-90)" strokeLinecap="round" />
      <circle r={TRACTOR_R} fill={color} stroke="#0a100c" strokeWidth={0.06} />
      <text y={0.11} fontSize={0.3} textAnchor="middle" fontWeight={800} fill="#0a100c">{t.id}</text>
      {t.status === 'broken' && <text y={-0.72} fontSize={0.42} textAnchor="middle">⚠️</text>}
      {t.status === 'working' && <text y={-0.68} fontSize={0.32} textAnchor="middle">⚙️</text>}
    </g>
  )
}

function plannedRoute(t: Tractor, run: RunSnapshot, map: MapInfo): Point[] {
  const jobsById = new Map(run.jobs.map((j) => [j.id, j]))
  const points: Point[] = [{ x: t.x, y: t.y }, ...t.path.map((n) => nodePos(map, n))]
  for (const jid of t.queue) {
    const job = jobsById.get(jid)
    if (job) points.push(nodePos(map, job.field_id))
  }
  return points
}

const toPath = (pts: Point[]) => pts.map((p, i) => `${i ? 'L' : 'M'}${p.x},${sy(p.y)}`).join(' ')

export function FieldMap({ run, map, highlight, handoffs = [], onSelectJob }: FieldMapProps) {
  const jobsByField = new Map<string, Job[]>()
  for (const j of run.jobs) jobsByField.set(j.field_id, [...(jobsByField.get(j.field_id) ?? []), j])
  const tractorsById = new Map(run.tractors.map((t) => [t.id, t]))

  return (
    <svg viewBox="-1 -1.2 12 12.4" className="h-full w-full select-none">
      <defs>
        {['done', ...run.tractors.map((t) => t.id)].map((id) => (
          <pattern key={id} id={`stripes-${id}`} width={0.3} height={0.3} patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
            <rect width={0.3} height={0.3} fill={id === 'done' ? '#2f6b3f' : `${tractorColor(id)}55`} />
            <rect width={0.14} height={0.3} fill={id === 'done' ? '#7bd88f' : tractorColor(id)} opacity={0.75} />
          </pattern>
        ))}
        <marker id="arrow" viewBox="0 0 10 10" refX={8} refY={5} markerWidth={4} markerHeight={4} orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#f2c46d" />
        </marker>
      </defs>

      {Array.from({ length: GRID + 1 }, (_, i) => (
        <g key={i} stroke="#ffffff08" strokeWidth={0.02}>
          <line x1={i} y1={0} x2={i} y2={GRID} />
          <line x1={0} y1={i} x2={GRID} y2={i} />
        </g>
      ))}

      {run.blocked_roads.map(([a, b]) => {
        const pa = nodePos(map, a)
        const pb = nodePos(map, b)
        const mx = (pa.x + pb.x) / 2
        const my = sy((pa.y + pb.y) / 2)
        return (
          <g key={`${a}-${b}`}>
            <line x1={pa.x} y1={sy(pa.y)} x2={pb.x} y2={sy(pb.y)} stroke="#ff5d5d" strokeWidth={0.08} strokeDasharray="0.2 0.15" opacity={0.8} />
            <text x={mx} y={my + 0.15} fontSize={0.45} textAnchor="middle">⛔</text>
          </g>
        )
      })}

      {map.fields.map((f) => (
        <FieldTile key={f.id} id={f.id} x={f.x} y={f.y} jobs={jobsByField.get(f.id) ?? []}
          highlighted={(jobsByField.get(f.id) ?? []).some((j) => highlight?.has(j.id))} onSelect={onSelectJob} />
      ))}

      <g>
        <rect x={map.depot.x - 0.6} y={sy(map.depot.y) - 0.35} width={1.2} height={0.7} rx={0.15} fill="#2c3d32" stroke="#4d6656" strokeWidth={0.04} />
        <text x={map.depot.x} y={sy(map.depot.y) + 0.1} fontSize={0.28} textAnchor="middle" fill="#cfe0d4" fontWeight={700}>DEPOT</text>
      </g>

      {run.tractors.filter((t) => t.status !== 'broken').map((t) => {
        const pts = plannedRoute(t, run, map)
        return pts.length > 1 ? (
          <path key={`route-${t.id}`} d={toPath(pts)} fill="none" stroke={tractorColor(t.id)} strokeWidth={0.06}
            className="route-dash" opacity={0.75} strokeLinejoin="round" />
        ) : null
      })}

      <AnimatePresence>
        {handoffs.map((h) => {
          const from = tractorsById.get(h.from)
          const to = tractorsById.get(h.to)
          if (!from || !to) return null
          const x1 = from.x, y1 = sy(from.y), x2 = to.x, y2 = sy(to.y)
          const cx = (x1 + x2) / 2 - (y2 - y1) * 0.35
          const cy = (y1 + y2) / 2 + (x2 - x1) * 0.35
          return (
            <motion.path key={h.key} d={`M${x1},${y1} Q${cx},${cy} ${x2},${y2}`} fill="none" stroke="#f2c46d"
              strokeWidth={0.1} markerEnd="url(#arrow)"
              initial={{ pathLength: 0, opacity: 1 }} animate={{ pathLength: 1, opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.9, ease: 'easeInOut' }} />
          )
        })}
      </AnimatePresence>

      {run.tractors.map((t) => <TractorMarker key={t.id} t={t} />)}
    </svg>
  )
}
