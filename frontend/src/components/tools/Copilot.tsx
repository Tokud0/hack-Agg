import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import type { ProposedEvent } from '../../types'
import { SourceBadge } from '../Panels'
import { describeEvent, errorText } from './shared'

interface Message {
  id: number
  role: 'operator' | 'copilot' | 'system'
  text: string
  events?: ProposedEvent[]
  source?: string
  resolved?: 'applied' | 'cancelled'
}

const SUGGESTIONS = [
  'T1 broke down near F1',
  'Road between F4 and F6 is flooded',
  'Make J04 urgent',
  'Which jobs are at risk?',
  'Which tractor has the most fuel?',
]

export function Copilot() {
  const [messages, setMessages] = useState<Message[]>([
    { id: 0, role: 'copilot', text: 'Ask about the fleet or report what is happening in the field. Reports become events you confirm; the coordinator then re-plans and checks safety.' },
  ])
  const [input, setInput] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages.length, isBusy])

  const push = (m: Omit<Message, 'id'>) => setMessages((prev) => [...prev, { ...m, id: prev.length + 1 }])
  const resolve = (id: number, resolved: Message['resolved']) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, resolved } : m)))

  const send = async (text: string) => {
    if (!text.trim() || isBusy) return
    const history = messages
      .filter((m): m is Message & { role: 'operator' | 'copilot' } => m.role !== 'system')
      .slice(-8)
      .map((m) => ({ role: m.role, text: m.text }))
    setInput('')
    push({ role: 'operator', text })
    setIsBusy(true)
    try {
      const res = await api.copilot(text, history)
      push({ role: 'copilot', text: res.reply, events: res.events, source: res.source })
    } catch (err) {
      push({ role: 'system', text: errorText(err) })
    } finally {
      setIsBusy(false)
    }
  }

  const apply = async (m: Message) => {
    try {
      for (const e of m.events ?? []) await api.event({ ...e, source: 'copilot' })
      resolve(m.id, 'applied')
    } catch (err) {
      push({ role: 'system', text: `Rejected by the coordinator: ${errorText(err)}` })
      resolve(m.id, 'cancelled')
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 space-y-2 overflow-y-auto pr-1">
        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              className={`max-w-[92%] rounded-xl px-3 py-2 text-[13px] ${m.role === 'operator' ? 'ml-auto bg-leaf/20 text-white' : m.role === 'system' ? 'bg-alarm/15 text-alarm' : 'bg-white/6 text-white/90'}`}>
              <div>{m.text}</div>
              {m.events && m.events.length > 0 && (
                <div className="mt-2 rounded-lg border border-wheat/30 bg-black/30 p-2">
                  <div className="text-[10px] uppercase tracking-widest text-wheat/80">Understood as</div>
                  {m.events.map((e, i) => <div key={i} className="text-[12px] text-wheat">{describeEvent(e)}</div>)}
                  {m.resolved ? (
                    <div className={`mt-1 text-[11px] ${m.resolved === 'applied' ? 'text-leaf' : 'text-white/40'}`}>
                      {m.resolved === 'applied' ? 'Applied. The coordinator re-planned.' : 'Cancelled'}
                    </div>
                  ) : (
                    <div className="mt-2 flex gap-2">
                      <button type="button" onClick={() => apply(m)} className="rounded-md bg-wheat px-2.5 py-1 text-xs font-bold text-black hover:brightness-110">Apply</button>
                      <button type="button" onClick={() => resolve(m.id, 'cancelled')} className="rounded-md bg-white/10 px-2.5 py-1 text-xs hover:bg-white/20">Cancel</button>
                    </div>
                  )}
                </div>
              )}
              {m.source && <div className="mt-1"><SourceBadge source={m.source} /></div>}
            </motion.div>
          ))}
        </AnimatePresence>
        {isBusy && <div className="blink text-xs text-white/40">● thinking…</div>}
        <div ref={endRef} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {SUGGESTIONS.map((s) => (
          <button type="button" key={s} onClick={() => send(s)} className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] text-white/55 hover:border-wheat/50 hover:text-wheat">{s}</button>
        ))}
      </div>
      <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); void send(input) }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} maxLength={500} placeholder="Ask or report, e.g. T3 is stuck at F5"
          className="flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-leaf/60" />
        <button type="submit" disabled={isBusy} className="rounded-lg bg-leaf px-3 text-sm font-bold text-black disabled:opacity-40">Send</button>
      </form>
    </div>
  )
}
