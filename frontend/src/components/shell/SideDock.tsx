import type { ReactNode } from 'react'
import { BoltIcon, ChatIcon, FlowIcon, ListIcon, ShieldIcon } from '../Icons'

export type DockTab = 'radio' | 'replan' | 'chat' | 'jobs' | 'events'

const TABS: { id: DockTab; label: string; icon: typeof ChatIcon }[] = [
  { id: 'radio', label: 'Radio', icon: FlowIcon },
  { id: 'replan', label: 'Re-plan', icon: ShieldIcon },
  { id: 'chat', label: 'Copilot', icon: ChatIcon },
  { id: 'jobs', label: 'Add jobs', icon: ListIcon },
  { id: 'events', label: 'Events', icon: BoltIcon },
]

interface SideDockProps {
  tab: DockTab
  onTab: (tab: DockTab) => void
  hasUnreadReplan: boolean
  panels: Record<DockTab, ReactNode>
}

/** Right-hand panel that stays put on every page. Panels stay mounted so the chat keeps its history. */
export function SideDock({ tab, onTab, hasUnreadReplan, panels }: SideDockProps) {
  return (
    <aside className="flex shrink-0 flex-col border-soil-700 bg-soil-900 p-3 max-xl:min-h-[600px] max-xl:border-t xl:w-[380px] xl:border-l">
      <div className="mb-3 grid grid-cols-5 gap-1 rounded-xl bg-black/30 p-1" role="tablist" aria-label="Coordinator tools">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button type="button" role="tab" aria-selected={tab === id} key={id} onClick={() => onTab(id)}
            className={`relative flex flex-col items-center gap-1 rounded-lg py-1.5 text-[10.5px] font-semibold ${tab === id ? 'bg-white/15 text-white' : 'text-white/45 hover:text-white'}`}>
            <Icon size={15} />{label}
            {id === 'replan' && hasUnreadReplan && <span className="absolute right-2 top-1.5 h-2 w-2 rounded-full bg-wheat" aria-label="new re-plan" />}
          </button>
        ))}
      </div>
      {TABS.map(({ id }) => (
        <div key={id} role="tabpanel" className={tab === id ? 'min-h-0 flex-1' : 'hidden'}>{panels[id]}</div>
      ))}
    </aside>
  )
}
