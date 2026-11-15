import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../../api'
import { tractorColor } from '../../theme'
import type { AgentMessage, MessagePhase } from '../../types'
import { ChatIcon } from '../Icons'
import { SourceBadge } from '../Panels'
import { Avatar, MessageRow } from './MessageRow'
import { agentColor, agentName, EVERYONE, isTractor } from '../../agents'
import { inputCls } from '../tools/shared'

const MAX_STAGGER_S = 1.2
const STAGGER_STEP_S = 0.025

const PHASES: { id: MessagePhase; title: string; hint: string }[] = [
  { id: 'situation', title: 'Situation', hint: 'What happened, the state of the roads, and where every tractor is' },
  { id: 'auction', title: 'Auction', hint: 'The Fleet Agent calls each job; tractors bid or pass; the winner gets a route and claims it' },
  { id: 'negotiation', title: 'Negotiation', hint: 'Tractors trade jobs between themselves when it improves the plan' },
  { id: 'approval', title: 'Approval', hint: 'The Safety Agent rules on the plan; tractors confirm their queues' },
]

/** Messages one agent sent or received, plus the calls it answered so its bids keep their context. */
function messagesOf(messages: AgentMessage[], agent: string): AgentMessage[] {
  if (agent === EVERYONE) return messages
  const own = messages.filter((m) => m.sender === agent || m.to === agent)
  const topics = new Set(own.map((m) => m.topic).filter(Boolean))
  return messages.filter((m) => own.includes(m) || (m.kind === 'announce' && topics.has(m.topic)))
}

function AskAgent({ tractorId, replanIndex }: { tractorId: string; replanIndex: number }) {
  const [question, setQuestion] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [reply, setReply] = useState<{ answer: string; source: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const ask = async (event: FormEvent) => {
    event.preventDefault()
    if (!question.trim() || isBusy) return
    setIsBusy(true)
    setError(null)
    try {
      setReply(await api.askAgent(tractorId, question.trim(), replanIndex))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The agent did not answer')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <div className="mt-2 border-t border-white/8 pt-2">
      <form onSubmit={ask} className="flex gap-2">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={300} aria-label={`Question for ${tractorId}`}
          placeholder={`Ask ${tractorId}'s agent about this round, e.g. why did you take that job?`} className={`${inputCls} min-w-0 flex-1`} />
        <button type="submit" disabled={isBusy || !question.trim()}
          className="rounded-md px-3 text-xs font-extrabold text-black disabled:opacity-40" style={{ background: tractorColor(tractorId) }}>{isBusy ? 'Asking…' : `Ask ${tractorId}`}</button>
      </form>
      {error && <p role="alert" className="mt-1.5 text-[12px] text-alarm">{error}</p>}
      {reply && (
        <div className="mt-2 flex gap-2 rounded-lg bg-white/5 px-2 py-1.5">
          <Avatar id={tractorId} />
          <p className="min-w-0 flex-1 text-[12.5px] leading-snug text-white/85">{reply.answer}</p>
          <span className="shrink-0 self-start"><SourceBadge source={reply.source} /></span>
        </div>
      )}
    </div>
  )
}

interface ConversationProps {
  /** Changes with the selected re-plan, so the feed replays its entrance. */
  replanIndex: number
  messages: AgentMessage[]
}

export function Conversation({ replanIndex, messages }: ConversationProps) {
  const [agent, setAgent] = useState(EVERYONE)
  const speakers = [...new Set(messages.map((m) => m.sender))]
  const selected = agent === EVERYONE || speakers.includes(agent) ? agent : EVERYONE
  const shown = messagesOf(messages, selected)

  return (
    <section className="panel flex max-h-[640px] min-h-[320px] flex-col p-3" aria-label="Agent conversation">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-white/60">
          <ChatIcon size={13} className="text-leaf" />Agent conversation
          <span className="rounded-full bg-white/10 px-1.5 py-px font-mono text-[10px] normal-case tracking-normal text-white/60">{shown.length} messages</span>
        </h2>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Listen to one agent">
          {[EVERYONE, ...speakers].map((id) => (
            <button type="button" key={id} aria-pressed={selected === id} onClick={() => setAgent(id)}
              className={`rounded-md border px-2 py-0.5 text-[11px] font-semibold ${selected === id ? 'border-white/30 bg-white/12 text-white' : 'border-white/10 text-white/50 hover:text-white'}`}
              style={selected === id && id !== EVERYONE ? { color: agentColor(id), borderColor: `${agentColor(id)}88` } : undefined}>
              {id === EVERYONE ? 'Everyone' : agentName(id)}
            </button>
          ))}
        </div>
      </div>

      <p className="mt-1.5 text-[11px] leading-snug text-white/45">
        <b className="text-white/65">Recorded trace.</b> Written down step by step while the Fleet Agent searched for this plan. Every number is computed by code; no LLM wrote these messages. Only the answer to &quot;Ask&quot; below comes from the LLM.
      </p>

      <div className="mt-2 min-h-0 flex-1 overflow-y-auto pr-1">
        {PHASES.map((phase, phaseIndex) => {
          const inPhase = shown.filter((m) => m.phase === phase.id)
          if (inPhase.length === 0) return null
          const before = shown.findIndex((m) => m.phase === phase.id)
          return (
            <div key={phase.id} className="mb-3">
              <div className="sticky top-0 z-10 flex items-baseline gap-2 bg-soil-800 py-1">
                <span className="font-mono text-[10px] font-bold text-white/40">{phaseIndex + 1}</span>
                <h3 className="text-[12px] font-extrabold text-white">{phase.title}</h3>
                <span className="text-[11px] text-white/40">{phase.hint}</span>
              </div>
              <ul>
                {inPhase.map((m, i) => (
                  <MessageRow key={`${replanIndex}-${selected}-${phase.id}-${i}`} message={m} delay={Math.min((before + i) * STAGGER_STEP_S, MAX_STAGGER_S)} />
                ))}
              </ul>
            </div>
          )
        })}
        {shown.length === 0 && <p className="py-6 text-center text-sm text-white/40">No messages recorded for this re-plan.</p>}
      </div>

      {isTractor(selected) && selected !== EVERYONE && <AskAgent key={`${selected}-${replanIndex}`} tractorId={selected} replanIndex={replanIndex} />}
    </section>
  )
}
