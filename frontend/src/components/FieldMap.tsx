import { AnimatePresence, motion } from 'framer-motion'
import { useId, useState } from 'react'
import { agentColor, agentName, EVERYONE } from '../agents'
import type { Speech } from '../radio'
import type { Job, MapInfo, RunSnapshot, Tractor } from '../types'
import { clock, tractorColor } from '../theme'

const GRID = 10
const FIELD_SIZE = 1.5
const TRACTOR_R = 0.36
const RING_R = 0.5
const RING_LEN = 2 * Math.PI * RING_R
const VIEW = { x: -1, y: -1.2, w: 12, h: 12.4 }

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
  /** The agent message being said right now, drawn over the map. */
  speech?: Speech | null
}

type Point = { x: number; y: number }
const sy = (y: number) => GRID - y

function nodePos(map: MapInfo, id: string): Point {
  if (id === map.depot.id) return { x: map.depot.x, y: map.depot.y }
  const f = map.fields.find((fl) => fl.id === id)
  return f ? { x: f.x, y: f.y } : { x: 0, y: 0 }
}

/* Tiny vector glyphs drawn in map units (no emoji). */
function DropGlyph({ x, y, color }: { x: number; y: number; color: string }) {
  return <path d={`M${x},${y - 0.16} q0.13,0.16 0.13,0.24 a0.13,0.13 0 0 1 -0.26,0 q0,-0.08 0.13,-0.24z`} fill={color} />
}
function GrassGlyph({ x, y, color }: { x: number; y: number; color: string }) {
  return (
    <path d={`M${x - 0.1},${y + 0.12} q0.02,-0.18 -0.04,-0.28 M${x},${y + 0.12} q0,-0.2 0.08,-0.32 M${x + 0.1},${y + 0.12} q0.02,-0.12 0.12,-0.2`}
      stroke={color} strokeWidth={0.045} fill="none" strokeLinecap="round" />
  )
}

const MARK = 0.13

/** A tick for finished work, a cross for work that will not get done; drawn in map units. */
function OutcomeMark({ x, y, isDone }: { x: number; y: number; isDone: boolean }) {
  const d = isDone
    ? `M${x - MARK},${y} l${MARK * 0.7},${MARK * 0.8} l${MARK * 1.3},-${MARK * 1.6}`
    : `M${x - MARK},${y - MARK} l${MARK * 2},${MARK * 2} M${x + MARK},${y - MARK} l-${MARK * 2},${MARK * 2}`
  return <path d={d} fill="none" stroke={isDone ? '#eafff0' : '#ff5d5d'} strokeWidth={0.07} strokeLinecap="round" strokeLinejoin="round" />
}

interface FieldTileProps {
  /** Unique per map, so two maps on one page never share SVG ids. */
  uid: string
  id: string
  x: number
  y: number
  jobs: Job[]
  highlighted: boolean
  onSelect?: (jobId: string) => void
}

/** One field. Each job on it has its own strip that fills as that job is worked, so a field with two jobs can be half done. */
function FieldTile({ uid, id, x, y, jobs, highlighted, onSelect }: FieldTileProps) {
  const half = FIELD_SIZE / 2
  const left = x - half
  const top = sy(y) - half
  const strip = FIELD_SIZE / Math.max(1, jobs.length)
  const isLost = jobs.length > 0 && jobs.every((j) => j.status === 'unassignable')
  return (
    <g className="cursor-pointer" onClick={() => jobs[0] && onSelect?.(jobs[0].id)}>
      {highlighted && (
        <motion.rect x={left - 0.18} y={top - 0.18} width={FIELD_SIZE + 0.36} height={FIELD_SIZE + 0.36} rx={0.35}
          fill="none" stroke="#f2c46d" strokeWidth={0.08}
          initial={{ opacity: 0 }} animate={{ opacity: [0.2, 1, 0.2] }} transition={{ repeat: Infinity, duration: 1.4 }} />
      )}
      <clipPath id={`${uid}-tile-${id}`}><rect x={left} y={top} width={FIELD_SIZE} height={FIELD_SIZE} rx={0.25} /></clipPath>
      <rect x={left} y={top} width={FIELD_SIZE} height={FIELD_SIZE} rx={0.25} fill="#1b2a20" />
      <g clipPath={`url(#${uid}-tile-${id})`}>
        {jobs.map((j, i) => {
          const x0 = left + i * strip
          const isMissed = j.status === 'unassignable'
          const pattern = j.status === 'in_progress' && j.tractor_id ? j.tractor_id : 'done'
          return (
            <g key={j.id}>
              {isMissed && <rect x={x0} y={top} width={strip} height={FIELD_SIZE} fill="#ff5d5d1f" />}
              <rect x={x0} y={top} width={strip * j.progress} height={FIELD_SIZE} fill={`url(#${uid}-stripes-${pattern})`}
                opacity={isMissed ? 0.45 : 1} style={{ transition: 'width 140ms linear' }} />
              {i > 0 && <line x1={x0} y1={top} x2={x0} y2={top + FIELD_SIZE} stroke="#0a100c" strokeWidth={0.05} />}
            </g>
          )
        })}
      </g>
      <rect x={left} y={top} width={FIELD_SIZE} height={FIELD_SIZE} rx={0.25} fill="none" stroke={isLost ? '#ff5d5d' : '#3a5243'}
        strokeWidth={isLost ? 0.07 : 0.04} strokeDasharray={isLost ? '0.15 0.1' : undefined} />
      <text x={left + 0.1} y={top + 0.32} fontSize={0.27} fill="#cfe0d4" fontWeight={700}>{id}</text>
      {jobs.map((j, i) => {
        const cx = left + i * strip + strip / 2
        const isDone = j.status === 'done'
        const isMissed = j.status === 'unassignable'
        const color = isDone ? '#eafff0' : isMissed ? '#ff8a8a' : '#9fc4ff'
        const gx = left + (i + 1) * strip - 0.2
        return (
          <g key={j.id}>
            {j.type === 'mow' ? <GrassGlyph x={gx} y={top + 0.24} color={color} /> : <DropGlyph x={gx} y={top + 0.26} color={color} />}
            {(isDone || isMissed) && <OutcomeMark x={cx} y={sy(y) + 0.02} isDone={isDone} />}
            <text x={cx} y={top + FIELD_SIZE - 0.14} fontSize={0.23} fill={color} textAnchor="middle" fontFamily="JetBrains Mono" fontWeight={isMissed ? 700 : 400}>{j.id}</text>
          </g>
        )
      })}
    </g>
  )
}

function TractorMarker({ t, onHover }: { t: Tractor; onHover: (id: string | null) => void }) {
  const color = t.status === 'broken' ? '#ff5d5d' : tractorColor(t.id)
  const fuelShare = Math.max(0, Math.min(1, t.fuel / t.fuel_capacity))
  const fuelColor = fuelShare < 0.2 ? '#ff5d5d' : fuelShare < 0.45 ? '#f2c46d' : '#7bd88f'
  return (
    <g style={{ transform: `translate(${t.x}px, ${sy(t.y)}px)`, transition: 'transform 140ms linear' }}
      onMouseEnter={() => onHover(t.id)} onMouseLeave={() => onHover(null)} className="cursor-help">
      {t.status === 'broken' && <circle className="pulse-ring" r={0.5} fill="none" stroke="#ff5d5d" strokeWidth={0.08} />}
      {t.status === 'working' && (
        <motion.circle r={0.62} fill="none" stroke={color} strokeWidth={0.04} strokeDasharray="0.12 0.12"
          animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 4, ease: 'linear' }} />
      )}
      <circle r={RING_R} fill="none" stroke="#ffffff14" strokeWidth={0.09} />
      <circle r={RING_R} fill="none" stroke={fuelColor} strokeWidth={0.09}
        strokeDasharray={`${RING_LEN * fuelShare} ${RING_LEN}`} transform="rotate(-90)" strokeLinecap="round" />
      <circle r={TRACTOR_R} fill={color} stroke="#0a100c" strokeWidth={0.06} />
      <text y={0.11} fontSize={0.3} textAnchor="middle" fontWeight={800} fill="#0a100c">{t.id}</text>
      {t.status === 'refueling' && (
        <g transform="translate(0,-0.86)">
          <motion.circle r={0.62} cy={0.86} fill="none" stroke="#f2c46d" strokeWidth={0.06}
            animate={{ opacity: [0.2, 1, 0.2] }} transition={{ repeat: Infinity, duration: 1 }} />
          <rect x={-0.13} y={-0.18} width={0.2} height={0.3} rx={0.03} fill="#f2c46d" stroke="#0a100c" strokeWidth={0.025} />
          <path d="M0.07,-0.1 h0.06 v0.16 a0.04,0.04 0 0 0 0.08,0 v-0.12" fill="none" stroke="#f2c46d" strokeWidth={0.03} />
        </g>
      )}
      {t.status === 'broken' && (
        <g transform="translate(0,-0.82)">
          <path d="M0,-0.24 L0.24,0.18 L-0.24,0.18 Z" fill="#ff5d5d" stroke="#0a100c" strokeWidth={0.03} />
          <rect x={-0.018} y={-0.1} width={0.036} height={0.15} fill="#0a100c" />
        </g>
      )}
    </g>
  )
}

function TractorTooltip({ t, run }: { t: Tractor; run: RunSnapshot }) {
  const left = ((t.x - VIEW.x) / VIEW.w) * 100
  const top = ((sy(t.y) - VIEW.y) / VIEW.h) * 100
  const job = run.jobs.find((j) => j.id === t.current_job)
  return (
    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }}
      className="pointer-events-none absolute z-10 w-48 -translate-x-1/2 -translate-y-[115%] rounded-lg border border-white/10 bg-soil-950/95 p-2.5 text-[11px] shadow-xl"
      style={{ left: `${left}%`, top: `${top}%` }}>
      <div className="flex items-center justify-between">
        <span className="font-bold" style={{ color: tractorColor(t.id) }}>{t.id} · {t.implement}</span>
        <span className={t.status === 'broken' ? 'text-alarm' : 'text-white/60'}>{t.status}</span>
      </div>
      <div className="mt-1 text-white/70">Fuel {Math.round(t.fuel)} / {t.fuel_capacity}{t.refuels ? ` · ${t.refuels} refuel${t.refuels > 1 ? 's' : ''}` : ''}</div>
      {t.refuel_stop && <div className="text-wheat">Refuelling at the depot first</div>}
      <div className="text-white/70">{job ? `Now: ${job.id} on ${job.field_id} (${Math.round(job.progress * 100)}%)` : 'No current job'}</div>
      <div className="text-white/50">Next: {t.queue.length ? t.queue.join(' → ') : '—'}</div>
      {job && <div className="text-white/40">Due {clock(job.deadline)}</div>}
    </motion.div>
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

const SPEECH_MAX_CHARS = 52
const SPEECH_CHAR_W = 0.125
const SPEECH_H = 0.92

/** Where an agent "is": a tractor agent rides its tractor, the other agents sit at the depot. */
function agentPoint(id: string, run: RunSnapshot, map: MapInfo): Point {
  const tractor = run.tractors.find((t) => t.id === id)
  return tractor ? { x: tractor.x, y: tractor.y } : { x: map.depot.x, y: map.depot.y }
}

function SpeechLayer({ speech, run, map }: { speech: Speech; run: RunSnapshot; map: MapInfo }) {
  const { sender, to, text } = speech.message
  const color = agentColor(sender)
  const from = agentPoint(sender, run, map)
  const listeners = to === EVERYONE
    ? run.tractors.filter((t) => t.id !== sender && t.status !== 'broken').map((t) => t.id)
    : to === 'operator' ? [] : [to]
  const line = text.length > SPEECH_MAX_CHARS ? `${text.slice(0, SPEECH_MAX_CHARS - 1)}…` : text
  const header = `${agentName(sender)} → ${agentName(to)}`
  const width = Math.max(line.length, header.length) * SPEECH_CHAR_W + 0.45
  const left = Math.min(Math.max(from.x - width / 2, VIEW.x + 0.1), VIEW.x + VIEW.w - width - 0.1)
  const above = sy(from.y) - 0.75 - SPEECH_H
  const top = above < VIEW.y + 0.05 ? sy(from.y) + 0.75 : above
  return (
    <g pointerEvents="none">
      {listeners.map((id) => {
        const target = agentPoint(id, run, map)
        return (
          <motion.line key={`${speech.id}-${id}`} x1={from.x} y1={sy(from.y)} x2={target.x} y2={sy(target.y)}
            stroke={color} strokeWidth={0.05} strokeLinecap="round"
            initial={{ pathLength: 0, opacity: 1 }} animate={{ pathLength: 1, opacity: 0.55 }} transition={{ duration: 0.35 }} />
        )
      })}
      <motion.circle key={`ring-${speech.id}`} cx={from.x} cy={sy(from.y)} fill="none" stroke={color} strokeWidth={0.06}
        initial={{ r: 0.45, opacity: 0.9 }} animate={{ r: 0.95, opacity: 0 }} transition={{ duration: 0.7 }} />
      <motion.g key={`bubble-${speech.id}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.12 }}>
        <rect x={left} y={top} width={width} height={SPEECH_H} rx={0.18} fill="#0a100cf2" stroke={color} strokeWidth={0.035} />
        <text x={left + 0.2} y={top + 0.34} fontSize={0.2} fontWeight={700} fill={color}>{header}</text>
        <text x={left + 0.2} y={top + 0.7} fontSize={0.235} fill="#e6efe8">{line}</text>
      </motion.g>
    </g>
  )
}

const toPath = (pts: Point[]) => pts.map((p, i) => `${i ? 'L' : 'M'}${p.x},${sy(p.y)}`).join(' ')

export function FieldMap({ run, map, highlight, handoffs = [], onSelectJob, speech }: FieldMapProps) {
  const [hovered, setHovered] = useState<string | null>(null)
  // Two maps can be on one page (Compare); their SVG ids must not collide, or one map draws with the other's shapes.
  const uid = `map${useId().replace(/[^a-zA-Z0-9]/g, '')}`
  const jobsByField = new Map<string, Job[]>()
  for (const j of run.jobs) jobsByField.set(j.field_id, [...(jobsByField.get(j.field_id) ?? []), j])
  const tractorsById = new Map(run.tractors.map((t) => [t.id, t]))
  const hoveredTractor = hovered ? tractorsById.get(hovered) : undefined

  return (
    <div className="relative h-full w-full">
      <svg viewBox={`${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}`} className="h-full w-full select-none">
        <defs>
          {['done', ...run.tractors.map((t) => t.id)].map((id) => (
            <pattern key={id} id={`${uid}-stripes-${id}`} width={0.3} height={0.3} patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
              <rect width={0.3} height={0.3} fill={id === 'done' ? '#2f6b3f' : `${tractorColor(id)}55`} />
              <rect width={0.14} height={0.3} fill={id === 'done' ? '#7bd88f' : tractorColor(id)} opacity={0.75} />
            </pattern>
          ))}
          <marker id={`${uid}-arrow`} viewBox="0 0 10 10" refX={8} refY={5} markerWidth={4} markerHeight={4} orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="#f2c46d" />
          </marker>
          <radialGradient id={`${uid}-soil-glow`} cx="50%" cy="45%" r="65%">
            <stop offset="0%" stopColor="#1d2c22" />
            <stop offset="100%" stopColor="#0f1712" />
          </radialGradient>
        </defs>

        <rect x={-0.5} y={-0.5} width={GRID + 1} height={GRID + 1} rx={0.4} fill={`url(#${uid}-soil-glow)`} />
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
              <circle cx={mx} cy={my} r={0.26} fill="#ff5d5d" stroke="#0a100c" strokeWidth={0.04} />
              <rect x={mx - 0.15} y={my - 0.04} width={0.3} height={0.08} fill="#0a100c" />
            </g>
          )
        })}

        {map.fields.map((f) => (
          <FieldTile key={f.id} uid={uid} id={f.id} x={f.x} y={f.y} jobs={jobsByField.get(f.id) ?? []}
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
              className="route-dash" opacity={hovered && hovered !== t.id ? 0.15 : 0.75} strokeLinejoin="round" />
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
                strokeWidth={0.1} markerEnd={`url(#${uid}-arrow)`}
                initial={{ pathLength: 0, opacity: 1 }} animate={{ pathLength: 1, opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.9, ease: 'easeInOut' }} />
            )
          })}
        </AnimatePresence>

        {run.tractors.map((t) => <TractorMarker key={t.id} t={t} onHover={setHovered} />)}
        {speech && <SpeechLayer speech={speech} run={run} map={map} />}
      </svg>
      <AnimatePresence>{hoveredTractor && <TractorTooltip key={hoveredTractor.id} t={hoveredTractor} run={run} />}</AnimatePresence>
    </div>
  )
}

export function MapLegend() {
  const item = 'flex items-center gap-1.5'
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10.5px] text-white/50">
      <span className={item}><svg width="22" height="6"><line x1="0" y1="3" x2="22" y2="3" stroke="#c792ea" strokeWidth="2" strokeDasharray="4 3" /></svg>planned route</span>
      <span className={item}><svg width="12" height="12"><circle cx="6" cy="6" r="4.5" fill="none" stroke="#7bd88f" strokeWidth="2" strokeDasharray="20 9" /></svg>fuel left</span>
      <span className={item}><span className="h-2.5 w-3.5 rounded-sm" style={{ background: 'repeating-linear-gradient(35deg,#7bd88f 0 3px,#2f6b3f 3px 6px)' }} />work in progress or done</span>
      <span className={item}><svg width="11" height="11" viewBox="0 0 11 11"><path d="M2 5.5l2.5 3 4.5-6" fill="none" stroke="#eafff0" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>job done</span>
      <span className={item}><svg width="11" height="11" viewBox="0 0 11 11"><path d="M2 2l7 7M9 2l-7 7" fill="none" stroke="#ff5d5d" strokeWidth="1.8" strokeLinecap="round" /></svg>job not done (deadline missed or no tractor)</span>
      <span className={item}><span className="h-2.5 w-2.5 rounded-full bg-alarm" />broken down</span>
      <span className={item}><span className="h-2.5 w-2.5 rounded-sm bg-wheat" />refuelling at depot</span>
    </div>
  )
}
