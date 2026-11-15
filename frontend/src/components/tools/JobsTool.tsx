import { AnimatePresence, motion } from 'framer-motion'
import { useRef, useState } from 'react'
import { api } from '../../api'
import type { JobDraft } from '../../types'
import { SHIFT_START_HOUR, clock } from '../../theme'
import { CloseIcon, PlusIcon, SparkIcon, UploadIcon } from '../Icons'
import { SourceBadge } from '../Panels'
import { errorText, inputCls } from './shared'

const DEFAULT_WORK_HOURS = 1.5
const DEFAULT_LEAD_HOURS = 4

interface JobsToolProps {
  fields: string[]
  nowHours: number
}

const toTimeInput = (hours: number) => clock(hours)
function fromTimeInput(value: string): number {
  const [h, m] = value.split(':').map(Number)
  return h + m / 60 - SHIFT_START_HOUR
}

export function JobsTool({ fields, nowHours }: JobsToolProps) {
  const [text, setText] = useState('')
  const [drafts, setDrafts] = useState<JobDraft[]>([])
  const [note, setNote] = useState<{ text: string; source: string } | null>(null)
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null)
  const [isBusy, setIsBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const update = (i: number, patch: Partial<JobDraft>) =>
    setDrafts((prev) => prev.map((d, idx) => (idx === i ? { ...d, ...patch } : d)))
  const addRow = () =>
    setDrafts((prev) => [...prev, {
      type: 'spray', field_id: fields[0], priority: 2,
      deadline_hours: Math.ceil(nowHours + DEFAULT_LEAD_HOURS), work_hours: DEFAULT_WORK_HOURS,
    }])

  const parse = async () => {
    if (!text.trim()) return
    setIsBusy(true)
    setStatus(null)
    try {
      const res = await api.parseJobs(text)
      setDrafts((prev) => [...prev, ...res.jobs])
      setNote({ text: res.note, source: res.source })
      if (res.jobs.length === 0) setStatus({ ok: false, text: 'No jobs recognised. Mention a field like F3.' })
    } catch (err) {
      setStatus({ ok: false, text: errorText(err) })
    } finally {
      setIsBusy(false)
    }
  }

  const submit = async () => {
    setIsBusy(true)
    const added: string[] = []
    try {
      for (const d of drafts) {
        const res = await api.addJob({ type: d.type, field_id: d.field_id, priority: d.priority, deadline: d.deadline_hours, work_hours: d.work_hours })
        added.push(res.job_id)
      }
      setDrafts([])
      setText('')
      setNote(null)
      setStatus({ ok: true, text: `Added ${added.join(', ')}. The coordinator re-planned.` })
    } catch (err) {
      setDrafts((prev) => prev.slice(added.length))
      setStatus({ ok: false, text: `${added.length ? `Added ${added.join(', ')}. ` : ''}Rejected: ${errorText(err)}` })
    } finally {
      setIsBusy(false)
    }
  }

  const upload = async (file: File) => {
    try {
      const scenario: unknown = JSON.parse(await file.text())
      const res = await api.uploadScenario(scenario)
      setStatus({ ok: true, text: `Loaded "${res.scenario}" with ${res.jobs} jobs. Press Run to start.` })
    } catch (err) {
      setStatus({ ok: false, text: `Could not load the file: ${errorText(err)}` })
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto pr-1 text-[13px]">
      <section>
        <label className="text-[11px] font-semibold uppercase tracking-wider text-white/50" htmlFor="job-text">Describe new work in plain words</label>
        <textarea id="job-text" value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={1000}
          placeholder="e.g. Mow F3 and F7 by 14:00, spray F2 urgently"
          className="mt-1 w-full resize-none rounded-lg border border-white/10 bg-black/30 px-3 py-2 outline-none focus:border-leaf/60" />
        <div className="mt-1.5 flex gap-2">
          <button type="button" onClick={parse} disabled={isBusy || !text.trim()}
            className="flex items-center gap-1.5 rounded-md bg-wheat px-3 py-1.5 text-xs font-bold text-black disabled:opacity-40">
            <SparkIcon size={12} />Turn into jobs
          </button>
          <button type="button" onClick={addRow} className="flex items-center gap-1 rounded-md bg-white/10 px-3 py-1.5 text-xs hover:bg-white/20">
            <PlusIcon size={12} />Add row manually
          </button>
        </div>
        {note && <div className="mt-1.5 flex items-start gap-2 text-[11px] text-white/45"><SourceBadge source={note.source} /><span>{note.text}</span></div>}
      </section>

      <AnimatePresence>
        {drafts.length > 0 && (
          <motion.section initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="rounded-lg border border-wheat/25 bg-wheat/5 p-2">
            <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-wheat/80">Check before adding</div>
            <div className="space-y-1.5">
              {drafts.map((d, i) => (
                <div key={i} className="grid grid-cols-[70px_64px_58px_78px_54px_20px] items-center gap-1">
                  <select aria-label="type" className={inputCls} value={d.type} onChange={(e) => update(i, { type: e.target.value as JobDraft['type'] })}>
                    <option value="spray">spray</option><option value="mow">mow</option>
                  </select>
                  <select aria-label="field" className={inputCls} value={d.field_id} onChange={(e) => update(i, { field_id: e.target.value })}>
                    {fields.map((f) => <option key={f}>{f}</option>)}
                  </select>
                  <select aria-label="priority" className={inputCls} value={d.priority} onChange={(e) => update(i, { priority: Number(e.target.value) })}>
                    {[1, 2, 3].map((p) => <option key={p} value={p}>P{p}</option>)}
                  </select>
                  <input aria-label="due" type="time" className={inputCls} value={toTimeInput(d.deadline_hours)}
                    onChange={(e) => e.target.value && update(i, { deadline_hours: fromTimeInput(e.target.value) })} />
                  <input aria-label="hours" type="number" min={0.25} max={8} step={0.25} className={inputCls} value={d.work_hours}
                    onChange={(e) => update(i, { work_hours: Number(e.target.value) })} />
                  <button type="button" aria-label="remove" onClick={() => setDrafts((prev) => prev.filter((_, idx) => idx !== i))} className="text-white/40 hover:text-alarm"><CloseIcon size={14} /></button>
                </div>
              ))}
            </div>
            <div className="mt-1 grid grid-cols-[70px_64px_58px_78px_54px_20px] gap-1 text-[9.5px] uppercase text-white/30">
              <span>type</span><span>field</span><span>priority</span><span>due</span><span>hours</span>
            </div>
            <button type="button" onClick={submit} disabled={isBusy}
              className="mt-2 w-full rounded-md bg-leaf py-1.5 text-xs font-extrabold text-black disabled:opacity-40">
              Add {drafts.length} job{drafts.length > 1 ? 's' : ''} to the plan
            </button>
          </motion.section>
        )}
      </AnimatePresence>

      {status && <div className={`rounded-md px-2.5 py-1.5 text-[12px] ${status.ok ? 'bg-leaf/10 text-leaf' : 'bg-alarm/10 text-alarm'}`}>{status.text}</div>}

      <section className="mt-auto border-t border-white/8 pt-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-white/50">Or load a whole job list</div>
        <p className="text-[11px] text-white/40">A scenario JSON with tractors, fields and jobs (same format as scenario.json). Restarts the shift.</p>
        <input ref={fileRef} type="file" accept="application/json,.json" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = '' }} />
        <button type="button" onClick={() => fileRef.current?.click()} className="mt-1.5 flex items-center gap-1.5 rounded-md bg-white/10 px-3 py-1.5 text-xs hover:bg-white/20">
          <UploadIcon size={12} />Upload JSON
        </button>
      </section>
    </div>
  )
}
