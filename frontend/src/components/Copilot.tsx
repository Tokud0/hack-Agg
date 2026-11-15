import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { api } from '../api'
import type { ProposedEvent } from '../types'

interface Message {
  id: number
  role: 'operator' | 'copilot' | 'system'
  text: string
  events?: ProposedEvent[]
  source?: string
  resolved?: 'applied' | 'cancelled'
}

const SUGGESTIONS = ['T1 broke down near F1', 'Road F4–F6 is flooded', 'J04 is urgent now', 'Why is J01 not planned?']

function describe(e: ProposedEvent): string {
  if (e.type === 'breakdown') return `breakdown(${e.tractor_id})`
  if (e.type === 'block_road') return `block_road(${e.a}, ${e.b})`
  return `change_priority(${e.job_id} → P${e.priority})`
}

const errorText = (err: unknown) => (err instanceof Error ? err.message : 'Something went wrong')

export function Copilot() {
  const [messages, setMessages] = useState<Message[]>([
    { id: 0, role: 'copilot', text: 'Tell me what is happening in the field. I translate it into events; the coordinator re-plans and verifies.' },
  ])
  const [input, setInput] = useState('')
  const [isBusy, setIsBusy] = useState(false)

  const push = (m: Omit<Message, 'id'>) => setMessages((prev) => [...prev, { ...m, id: prev.length + 1 }])
  const resolve = (id: number, resolved: Message['resolved']) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, resolved } : m)))

  const send = async (text: string) => {
    if (!text.trim() || isBusy) return
    setInput('')
    push({ role: 'operator', text })
    setIsBusy(true)
    try {
      const res = await api.copilot(text)
      push({ role: 'copilot', text: res.reply, events: res.events, source: res.source })
    } catch (err) {
      push({ role: 'system', text: errorText(err) })
    } finally {
      setIsBusy(false)
    }
  }

  const apply = async (m: Message) => {
    try {
      for (const e of m.events ?? []) await api.event(e)
      resolve(m.id, 'applied')
    } catch (err) {
      push({ role: 'system', text: `Rejected by coordinator: ${errorText(err)}` })
      resolve(m.id, 'cancelled')
    }
  }

  return (
    <div className="panel flex h-full min-h-0 flex-col p-3">
      <h3 className="mb-2 text-xs font-bold uppercase tracking-widest text-white/60">Dispatch copilot</h3>
      <div className="flex-1 space-y-2 overflow-y-auto pr-1">
        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              className={`max-w-[92%] rounded-xl px-3 py-2 text-[13px] ${m.role === 'operator' ? 'ml-auto bg-leaf/20 text-white' : m.role === 'system' ? 'bg-alarm/15 text-alarm' : 'bg-white/6 text-white/90'}`}>
              <div>{m.text}</div>
              {m.events && m.events.length > 0 && (
                <div className="mt-2 rounded-lg border border-wheat/30 bg-black/30 p-2">
                  <div className="text-[10px] uppercase tracking-widest text-wheat/80">Understood as</div>
                  {m.events.map((e, i) => <div key={i} className="font-mono text-[12px] text-wheat">{describe(e)}</div>)}
                  {m.resolved ? (
                    <div className={`mt-1 text-[11px] ${m.resolved === 'applied' ? 'text-leaf' : 'text-white/40'}`}>
                      {m.resolved === 'applied' ? '✓ applied — coordinator re-planned' : 'cancelled'}
                    </div>
                  ) : (
                    <div className="mt-2 flex gap-2">
                      <button type="button" onClick={() => apply(m)} className="rounded-md bg-wheat px-2.5 py-1 text-xs font-bold text-black hover:brightness-110">Apply</button>
                      <button type="button" onClick={() => resolve(m.id, 'cancelled')} className="rounded-md bg-white/10 px-2.5 py-1 text-xs hover:bg-white/20">Cancel</button>
                    </div>
                  )}
                </div>
              )}
              {m.source && <div className="mt-1 text-[10px] text-white/30">{m.source === 'claude' ? '✦ Claude' : 'offline parser'}</div>}
            </motion.div>
          ))}
        </AnimatePresence>
        {isBusy && <div className="blink text-xs text-white/40">● thinking…</div>}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {SUGGESTIONS.map((s) => (
          <button type="button" key={s} onClick={() => send(s)} className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-white/55 hover:border-wheat/50 hover:text-wheat">{s}</button>
        ))}
      </div>
      <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); void send(input) }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} maxLength={500} placeholder="e.g. T3 is stuck at F5"
          className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-leaf/60" />
        <button type="submit" disabled={isBusy} className="rounded-lg bg-leaf px-3 text-sm font-bold text-black disabled:opacity-40">Send</button>
      </form>
    </div>
  )
}
