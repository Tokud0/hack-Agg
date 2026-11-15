import { tractorColor } from './theme'

export const EVERYONE = 'all'

/** The non-tractor agents; a tractor agent is named and coloured after its tractor. */
export const AGENT: Record<string, { name: string; short: string; color: string }> = {
  fleet_agent: { name: 'Fleet Agent', short: 'F', color: '#7bd88f' },
  navigation_agent: { name: 'Navigation Agent', short: 'N', color: '#f5a3c7' },
  safety_agent: { name: 'Safety Agent', short: 'S', color: '#7dd3fc' },
  explainer: { name: 'Explainer', short: 'E', color: '#f2c46d' },
  operator: { name: 'operator', short: '', color: '#9aa79e' },
  all: { name: 'everyone', short: '', color: '#9aa79e' },
}

export const agentName = (id: string): string => AGENT[id]?.name ?? id
export const agentColor = (id: string): string => AGENT[id]?.color ?? tractorColor(id)
export const isTractor = (id: string): boolean => !(id in AGENT)
