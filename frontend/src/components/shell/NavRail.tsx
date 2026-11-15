import type { View } from '../../nav'
import { ChartIcon, FlowIcon, ListIcon, MapIcon, TimelineIcon } from '../Icons'

const ITEMS: { id: View; label: string; hint: string; icon: typeof MapIcon }[] = [
  { id: 'live', label: 'Live', hint: 'Map and fleet right now', icon: MapIcon },
  { id: 'orchestration', label: 'Agents', hint: 'How the agents turn an event into a safe plan', icon: FlowIcon },
  { id: 'schedule', label: 'Schedule', hint: 'Timeline and job list', icon: TimelineIcon },
  { id: 'compare', label: 'Compare', hint: 'Our coordinator against simple dispatch rules', icon: ChartIcon },
  { id: 'log', label: 'Log', hint: 'Every event and decision of the shift', icon: ListIcon },
]

interface NavRailProps {
  view: View
  onNavigate: (view: View) => void
}

export function NavRail({ view, onNavigate }: NavRailProps) {
  return (
    <nav aria-label="Pages" className="flex shrink-0 gap-1 border-soil-700 bg-soil-900 p-2 max-xl:border-b xl:w-[84px] xl:flex-col xl:border-r">
      {ITEMS.map(({ id, label, hint, icon: Icon }) => {
        const isActive = view === id
        return (
          <button type="button" key={id} title={hint} aria-current={isActive ? 'page' : undefined} onClick={() => onNavigate(id)}
            className={`relative flex flex-1 items-center justify-center gap-1.5 rounded-xl px-2 py-2.5 text-[11.5px] font-semibold transition-colors xl:flex-none xl:flex-col ${isActive ? 'bg-leaf/12 text-leaf' : 'text-white/50 hover:bg-white/5 hover:text-white'}`}>
            {isActive && <span className="absolute inset-y-2 left-0 hidden w-0.5 rounded-full bg-leaf xl:block" />}
            <Icon size={20} />
            {label}
          </button>
        )
      })}
    </nav>
  )
}
