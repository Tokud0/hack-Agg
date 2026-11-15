import type { ReactNode } from 'react'

interface ViewHeaderProps {
  title: string
  description: string
  actions?: ReactNode
}

export function ViewHeader({ title, description, actions }: ViewHeaderProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h1 className="text-lg font-extrabold tracking-tight">{title}</h1>
        <p className="text-[12.5px] text-white/50">{description}</p>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

interface SegmentedProps<T extends string> {
  label: string
  options: { id: T; label: string }[]
  value: T
  onChange: (value: T) => void
}

export function Segmented<T extends string>({ label, options, value, onChange }: SegmentedProps<T>) {
  return (
    <div className="flex rounded-lg bg-black/30 p-0.5 text-[11.5px]" role="group" aria-label={label}>
      {options.map((o) => (
        <button type="button" key={o.id} aria-pressed={value === o.id} onClick={() => onChange(o.id)}
          className={`rounded-md px-2.5 py-1 font-semibold ${value === o.id ? 'bg-white/15 text-white' : 'text-white/45 hover:text-white'}`}>{o.label}</button>
      ))}
    </div>
  )
}
