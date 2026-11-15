import { useEffect, useState } from 'react'

export type View = 'live' | 'orchestration' | 'schedule' | 'compare' | 'log'

const VIEW_IDS: View[] = ['live', 'orchestration', 'schedule', 'compare', 'log']
const DEFAULT_VIEW: View = 'live'

function viewFromHash(): View {
  const id = window.location.hash.slice(1)
  return VIEW_IDS.includes(id as View) ? (id as View) : DEFAULT_VIEW
}

/** Current page kept in the URL hash, so a refresh or a shared link lands on the same page. */
export function useHashView(): [View, (view: View) => void] {
  const [view, setView] = useState<View>(viewFromHash)
  useEffect(() => {
    const onHashChange = () => setView(viewFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])
  const navigate = (next: View) => {
    window.location.hash = next
  }
  return [view, navigate]
}
