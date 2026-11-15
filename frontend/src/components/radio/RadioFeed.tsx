import { useEffect, useRef } from 'react'
import type { RadioItem } from '../../radio'
import { clock } from '../../theme'
import { MessageRow } from '../orchestration/MessageRow'

const MAX_ROWS = 160
/** Keep following the newest message only while the reader is already near the bottom. */
const FOLLOW_WITHIN_PX = 140

interface RadioFeedProps {
  items: RadioItem[]
  backlog: number
}

/** Live feed of what the agents say to each other, newest at the bottom. */
export function RadioFeed({ items, backlog }: RadioFeedProps) {
  const scroller = useRef<HTMLDivElement>(null)
  const rows = items.slice(-MAX_ROWS)

  useEffect(() => {
    const el = scroller.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_WITHIN_PX + 80) el.scrollTop = el.scrollHeight
  }, [items.length])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-white/60">
          <span className={`h-2 w-2 rounded-full bg-leaf ${backlog ? 'blink' : ''}`} />Agent radio
        </h2>
        <span className="font-mono text-[10.5px] text-white/40">{backlog ? `${backlog} more coming` : `${items.length} messages`}</span>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-white/45">
        Status calls arrive as they happen. A re-plan is decided in milliseconds; its conversation is the recorded trace, played back slowly so you can follow it on the map.
      </p>
      <div ref={scroller} className="mt-2 min-h-0 flex-1 overflow-y-auto pr-1" aria-live="off">
        {rows.length === 0 && <p className="py-6 text-center text-sm text-white/40">Quiet so far. Press Run.</p>}
        <ul>
          {rows.map((item) => item.message ? (
            <MessageRow key={item.id} message={item.message} />
          ) : (
            <li key={item.id} className="sticky top-0 z-10 mt-3 flex items-baseline gap-2 border-t border-white/10 bg-soil-900 py-1.5">
              <span className="font-mono text-[10.5px] text-leaf">{clock(item.time)}</span>
              <span className="text-[12px] font-extrabold text-white">{item.title}</span>
              <span className="ml-auto text-[10px] text-white/40">{item.note}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
