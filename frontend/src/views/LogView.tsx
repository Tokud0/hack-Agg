import { DownloadIcon } from '../components/Icons'
import { EventLog } from '../components/Panels'
import { ViewHeader } from '../components/shell/ViewHeader'
import type { LogEntry } from '../types'

export function LogView({ log }: { log: LogEntry[] }) {
  return (
    <div className="flex h-full flex-col gap-3">
      <ViewHeader title="Log" description="Every event, re-plan and finished job of this shift, newest first."
        actions={<a href="/api/export" download="event-log.json"
          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/70 hover:bg-white/10 hover:text-white"><DownloadIcon size={14} />Download event log</a>} />
      <section className="panel flex min-h-[320px] flex-1 flex-col p-3" aria-label="Event log">
        {log.length === 0
          ? <p className="m-auto text-sm text-white/40">Nothing yet. Press Run to start the shift.</p>
          : <div className="min-h-0 flex-1"><EventLog log={log} /></div>}
      </section>
    </div>
  )
}
