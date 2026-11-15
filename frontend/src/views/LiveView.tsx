import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { FieldMap, MapLegend, type Handoff } from '../components/FieldMap'
import { FleetStrip } from '../components/FleetStrip'
import { CloseIcon } from '../components/Icons'
import { Counters } from '../components/Panels'
import { ViewHeader } from '../components/shell/ViewHeader'
import { BASELINES, type BaselineKind } from '../strategies'
import type { MapInfo, Metrics, RunSnapshot } from '../types'

const COORDINATOR_ACCENT = '#7bd88f'

const GUIDE = [
  'Press Run to start the shift',
  'Break a tractor on its card and watch the re-plan',
  'Click any field or job to see why it went there',
  'Ask the copilot or forecast "what if" on the right',
]

function Guide({ onClose }: { onClose: () => void }) {
  return (
    <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
      className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded-xl border border-leaf/20 bg-leaf/5 px-4 py-2 text-[12.5px]">
      <span className="font-bold text-leaf">How to use</span>
      {GUIDE.map((text, i) => (
        <span key={text} className="flex items-center gap-2 text-white/75">
          <span className="grid h-5 w-5 place-items-center rounded-full bg-leaf/20 text-[11px] font-bold text-leaf">{i + 1}</span>{text}
        </span>
      ))}
      <button type="button" onClick={onClose} aria-label="Hide guide" className="ml-auto text-white/40 hover:text-white"><CloseIcon size={14} /></button>
    </motion.div>
  )
}

interface LiveViewProps {
  run: RunSnapshot
  map: MapInfo
  baselineKind: BaselineKind
  baselineMetrics: Metrics
  highlight: Set<string>
  handoffs: Handoff[]
  lastWords: Record<string, string>
  onBreak: (tractorId: string) => void
  onSelectJob: (jobId: string) => void
}

export function LiveView({ run, map, baselineKind, baselineMetrics, highlight, handoffs, lastWords, onBreak, onSelectJob }: LiveViewProps) {
  const [showGuide, setShowGuide] = useState(true)
  return (
    <div className="flex h-full flex-col gap-3">
      <ViewHeader title="Live" description="Where every tractor is right now and what it does next."
        actions={<span className="text-[11px] text-white/40">green / red badges: difference vs {BASELINES[baselineKind].label}</span>} />
      <AnimatePresence>{showGuide && <Guide onClose={() => setShowGuide(false)} />}</AnimatePresence>
      <Counters metrics={run.metrics} accent={COORDINATOR_ACCENT} compareTo={baselineMetrics} />
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_300px]">
        <section className="panel flex min-h-[420px] flex-col p-3" aria-label="Field map">
          <div className="min-h-0 flex-1">
            <FieldMap run={run} map={map} highlight={highlight} handoffs={handoffs} onSelectJob={onSelectJob} />
          </div>
          <div className="mt-2"><MapLegend /></div>
        </section>
        <section className="flex min-h-0 flex-col" aria-label="Fleet status">
          <h2 className="mb-2 px-1 text-xs font-bold uppercase tracking-widest text-white/60">Fleet · one agent per tractor</h2>
          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            <FleetStrip tractors={run.tractors} jobs={run.jobs} onBreak={onBreak} onSelectJob={onSelectJob} isStacked lastWords={lastWords} />
          </div>
        </section>
      </div>
    </div>
  )
}
