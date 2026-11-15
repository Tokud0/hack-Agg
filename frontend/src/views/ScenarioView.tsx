import { useEffect, useState } from 'react'
import { api } from '../api'
import { PlayIcon, ResetIcon, ShuffleIcon, SparkIcon } from '../components/Icons'
import { SourceBadge } from '../components/Panels'
import { JobList, TractorList } from '../components/scenario/ScenarioLists'
import { ScenarioMap } from '../components/scenario/ScenarioMap'
import { ViewHeader } from '../components/shell/ViewHeader'
import { inputCls } from '../components/tools/shared'
import {
  EMPTY_SCENARIO, MAX_FIELDS, checkScenario, movedField, updatedJob, updatedTractor, withField, withJob, withTractor,
  withoutField, withoutJob, withoutTractor, type Scenario,
} from '../scenario'

const EXAMPLE = 'Two sprayers and one mower, 6 fields. Spray four of them, two are urgent and due by 10:00. Mow the other two by the afternoon.'

const ghostButton = 'flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/70 hover:bg-white/10 hover:text-white disabled:opacity-40'

const errorText = (e: unknown): string => (e instanceof Error ? e.message : 'Something went wrong')

interface ScenarioViewProps {
  /** Called once the new shift is loaded and ready to run. */
  onStarted: () => void
}

export function ScenarioView({ onStarted }: ScenarioViewProps) {
  const [scenario, setScenario] = useState<Scenario>(EMPTY_SCENARIO)
  const [selectedField, setSelectedField] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string; source?: string } | null>(null)

  /** Run a request that yields a scenario and put the result into the editor. */
  const load = async (fetchScenario: () => Promise<{ scenario: Scenario; source?: string }>, done: string) => {
    setIsBusy(true)
    setNote(null)
    try {
      const { scenario: next, source } = await fetchScenario()
      setScenario(next)
      setSelectedField(null)
      setNote({ ok: true, text: done, source })
    } catch (e) {
      setNote({ ok: false, text: errorText(e) })
    } finally {
      setIsBusy(false)
    }
  }

  // Start from the shift that is running, so there is always something to edit.
  useEffect(() => {
    api.currentScenario().then(setScenario).catch((e: unknown) => setNote({ ok: false, text: errorText(e) }))
  }, [])

  const start = async () => {
    setIsBusy(true)
    try {
      await api.uploadScenario(scenario)
      onStarted()
    } catch (e) {
      setNote({ ok: false, text: `The shift could not start: ${errorText(e)}` })
    } finally {
      setIsBusy(false)
    }
  }

  const removeField = (id: string) => {
    setScenario((s) => withoutField(s, id))
    setSelectedField(null)
  }

  const { blockers, warnings } = checkScenario(scenario)
  const canAddField = scenario.fields.length < MAX_FIELDS

  return (
    <div className="flex h-full flex-col gap-3">
      <ViewHeader title="Scenario" description="Build your own shift: describe it, roll a random one, or place fields and jobs by hand."
        actions={<>
          <button type="button" className={ghostButton} disabled={isBusy} onClick={() => load(async () => ({ scenario: await api.randomScenario() }), 'Random shift generated. Change anything, then start it.')}><ShuffleIcon size={14} />Random</button>
          <button type="button" className={ghostButton} disabled={isBusy} onClick={() => { setScenario(EMPTY_SCENARIO); setSelectedField(null); setNote(null) }}><ResetIcon size={14} />Clear</button>
          <button type="button" onClick={start} disabled={isBusy || blockers.length > 0}
            className="flex items-center gap-1.5 rounded-lg bg-leaf px-4 py-1.5 text-xs font-extrabold text-black hover:brightness-110 disabled:opacity-40"><PlayIcon size={13} />Start this shift</button>
        </>} />

      <section className="panel p-3" aria-label="Describe the shift">
        <label htmlFor="scenario-text" className="text-xs font-bold uppercase tracking-widest text-white/60">Describe it in plain words</label>
        <div className="mt-1.5 flex gap-2">
          <textarea id="scenario-text" value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={2000} placeholder={EXAMPLE}
            className="min-w-0 flex-1 resize-none rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-[13px] outline-none focus:border-leaf/60" />
          <button type="button" disabled={isBusy || text.trim().length < 3}
            onClick={() => load(() => api.describeScenario(text.trim()), 'Built from your description. Check it on the map, then start it.')}
            className="flex items-center gap-1.5 self-stretch rounded-lg bg-wheat px-3 text-xs font-extrabold text-black hover:brightness-110 disabled:opacity-40"><SparkIcon size={13} />{isBusy ? 'Building…' : 'Build it'}</button>
        </div>
        {note && (
          <p role={note.ok ? undefined : 'alert'} className={`mt-1.5 flex items-center gap-2 text-[12px] ${note.ok ? 'text-leaf' : 'text-alarm'}`}>
            {note.text}{note.source && <SourceBadge source={note.source} />}
          </p>
        )}
      </section>

      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <section className="panel flex min-h-[380px] flex-col p-3" aria-label="Field layout">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-xs font-bold uppercase tracking-widest text-white/60">Fields <span className="font-mono text-white/35">{scenario.fields.length}/{MAX_FIELDS}</span></h2>
            {selectedField
              ? <button type="button" onClick={() => removeField(selectedField)} className="rounded-md border border-alarm/40 px-2 py-1 text-[11.5px] font-semibold text-alarm hover:bg-alarm/15">Remove {selectedField} and its jobs</button>
              : <span className="text-[11px] text-white/45">{canAddField ? 'Click an empty spot to place a field. Drag a field to move it.' : 'Field limit reached.'}</span>}
          </div>
          <div className="mt-2 min-h-0 flex-1">
            <ScenarioMap scenario={scenario} selectedField={selectedField} onSelectField={setSelectedField}
              onAddField={(x, y) => setScenario((s) => withField(s, x, y))} onMoveField={(id, x, y) => setScenario((s) => movedField(s, id, x, y))} />
          </div>
        </section>

        <section className="panel flex min-h-0 flex-col gap-3 overflow-y-auto p-3" aria-label="Shift contents">
          <div>
            <label htmlFor="scenario-name" className="text-xs font-bold uppercase tracking-widest text-white/60">Name</label>
            <input id="scenario-name" value={scenario.name} maxLength={60} onChange={(e) => setScenario((s) => ({ ...s, name: e.target.value }))} className={`${inputCls} mt-1 w-full`} />
          </div>
          <TractorList tractors={scenario.tractors} onAdd={() => setScenario(withTractor)}
            onUpdate={(id, patch) => setScenario((s) => updatedTractor(s, id, patch))} onRemove={(id) => setScenario((s) => withoutTractor(s, id))} />
          <JobList scenario={scenario} selectedField={selectedField} onAdd={(fieldId) => setScenario((s) => withJob(s, fieldId))}
            onUpdate={(id, patch) => setScenario((s) => updatedJob(s, id, patch))} onRemove={(id) => setScenario((s) => withoutJob(s, id))} />
          {(blockers.length > 0 || warnings.length > 0) && (
            <ul className="space-y-0.5 text-[12px]">
              {blockers.map((b) => <li key={b} className="text-alarm">{b}</li>)}
              {warnings.map((w) => <li key={w} className="text-wheat">{w}</li>)}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
