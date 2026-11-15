import { MapLegend, type Handoff } from '../components/FieldMap'
import { ChartIcon } from '../components/Icons'
import { JobChipsLegend } from '../components/JobChips'
import { MapPanel } from '../components/MapPanel'
import { Segmented, ViewHeader } from '../components/shell/ViewHeader'
import { BASELINES, BASELINE_OPTIONS, type BaselineKind } from '../strategies'
import type { Speech } from '../radio'
import type { MapInfo, RunSnapshot } from '../types'

interface CompareViewProps {
  coordinator: RunSnapshot
  baseline: RunSnapshot
  baselineKind: BaselineKind
  onBaselineKind: (kind: BaselineKind) => void
  map: MapInfo
  highlight: Set<string>
  handoffs: Handoff[]
  onSelectJob: (jobId: string) => void
  onOpenBenchmark: () => void
  speech: Speech | null
}

const NO_HIGHLIGHT = new Set<string>()

export function CompareView({ coordinator, baseline, baselineKind, onBaselineKind, map, highlight, handoffs, onSelectJob, onOpenBenchmark, speech }: CompareViewProps) {
  return (
    <div className="flex h-full flex-col gap-3">
      <ViewHeader title="Compare" description="Same shift, same events: a simple dispatch rule on the left, our coordinator on the right."
        actions={<>
          <span className="text-[11px] text-white/40">Compare against</span>
          <Segmented label="Baseline rule" options={BASELINE_OPTIONS} value={baselineKind} onChange={onBaselineKind} />
          <button type="button" onClick={onOpenBenchmark}
            className="flex items-center gap-1.5 rounded-lg bg-wheat px-3 py-1.5 text-xs font-extrabold text-black hover:brightness-110"><ChartIcon size={14} />Benchmark on 50 shifts</button>
        </>} />
      <div className="grid min-h-0 flex-1 gap-3 md:grid-cols-2">
        <MapPanel run={baseline} map={map} accent="#8fa396" title={`Baseline · ${BASELINES[baselineKind].short}`} subtitle={BASELINES[baselineKind].subtitle}
          highlight={NO_HIGHLIGHT} handoffs={[]} onSelectJob={onSelectJob} compareJobs={coordinator.jobs} />
        <MapPanel run={coordinator} map={map} accent="#7bd88f" title="Our coordinator" subtitle="constraint-safe re-planning"
          highlight={highlight} handoffs={handoffs} compareTo={baseline.metrics} onSelectJob={onSelectJob} speech={speech} compareJobs={baseline.jobs} />
      </div>
      <div className="flex flex-col gap-1"><JobChipsLegend hasComparison /><MapLegend /></div>
    </div>
  )
}
