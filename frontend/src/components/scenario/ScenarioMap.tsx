import { useRef, useState } from 'react'
import type { PointerEvent } from 'react'
import { GRID, isFree, type Scenario } from '../../scenario'

const VIEW = { x: -1, y: -1.2, w: 12, h: 12.4 }
const FIELD_SIZE = 1.5
const sy = (y: number) => GRID - y

interface ScenarioMapProps {
  scenario: Scenario
  selectedField: string | null
  onSelectField: (id: string | null) => void
  onAddField: (x: number, y: number) => void
  onMoveField: (id: string, x: number, y: number) => void
}

/** Editable map: click an empty cell to place a field, drag a field to move it. */
export function ScenarioMap({ scenario, selectedField, onSelectField, onAddField, onMoveField }: ScenarioMapProps) {
  const svg = useRef<SVGSVGElement>(null)
  const [dragging, setDragging] = useState<string | null>(null)
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null)

  const cellAt = (event: PointerEvent): { x: number; y: number } | null => {
    const matrix = svg.current?.getScreenCTM()
    if (!svg.current || !matrix) return null
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    return { x: Math.round(point.x), y: GRID - Math.round(point.y) }
  }

  const handleMove = (event: PointerEvent) => {
    const cell = cellAt(event)
    if (!cell) return
    if (dragging) onMoveField(dragging, cell.x, cell.y)
    setHover(!dragging && isFree(scenario, cell.x, cell.y) ? cell : null)
  }

  const handleBackgroundClick = (event: PointerEvent) => {
    const cell = cellAt(event)
    if (cell && isFree(scenario, cell.x, cell.y)) onAddField(cell.x, cell.y)
    else onSelectField(null)
  }

  const jobCount = (fieldId: string) => scenario.jobs.filter((j) => j.field_id === fieldId).length

  return (
    <svg ref={svg} viewBox={`${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}`} className="h-full w-full touch-none select-none"
      onPointerMove={handleMove} onPointerUp={() => setDragging(null)} onPointerLeave={() => { setDragging(null); setHover(null) }}>
      <rect x={-0.5} y={-0.5} width={GRID + 1} height={GRID + 1} rx={0.4} fill="#16211a" onPointerDown={handleBackgroundClick} className="cursor-crosshair" />
      {Array.from({ length: GRID + 1 }, (_, i) => (
        <g key={i} stroke="#ffffff10" strokeWidth={0.02} pointerEvents="none">
          <line x1={i} y1={0} x2={i} y2={GRID} />
          <line x1={0} y1={i} x2={GRID} y2={i} />
        </g>
      ))}
      {hover && (
        <rect x={hover.x - FIELD_SIZE / 2} y={sy(hover.y) - FIELD_SIZE / 2} width={FIELD_SIZE} height={FIELD_SIZE} rx={0.25}
          fill="#7bd88f14" stroke="#7bd88f" strokeWidth={0.04} strokeDasharray="0.15 0.12" pointerEvents="none" />
      )}
      <g pointerEvents="none">
        <rect x={scenario.depot.x - 0.75} y={sy(scenario.depot.y) - 0.35} width={1.5} height={0.7} rx={0.15} fill="#1f2d24" stroke="#8fa396" strokeWidth={0.04} />
        <text x={scenario.depot.x} y={sy(scenario.depot.y) + 0.1} fontSize={0.3} fontWeight={700} textAnchor="middle" fill="#cfe0d4">DEPOT</text>
      </g>
      {scenario.fields.map((f) => {
        const isSelected = f.id === selectedField
        const jobs = jobCount(f.id)
        return (
          <g key={f.id} className={dragging === f.id ? 'cursor-grabbing' : 'cursor-grab'}
            onPointerDown={(e) => { e.stopPropagation(); onSelectField(f.id); setDragging(f.id); setHover(null) }}>
            <rect x={f.x - FIELD_SIZE / 2} y={sy(f.y) - FIELD_SIZE / 2} width={FIELD_SIZE} height={FIELD_SIZE} rx={0.25}
              fill={isSelected ? '#2f6b3f' : '#1b2a20'} stroke={isSelected ? '#7bd88f' : '#3a5243'} strokeWidth={isSelected ? 0.08 : 0.04} />
            <text x={f.x} y={sy(f.y) - 0.05} fontSize={0.38} fontWeight={800} textAnchor="middle" fill="#e6efe8">{f.id}</text>
            <text x={f.x} y={sy(f.y) + 0.4} fontSize={0.24} textAnchor="middle" fill={jobs ? '#9fc4ff' : '#ffffff55'}>
              {jobs ? `${jobs} job${jobs === 1 ? '' : 's'}` : 'no jobs'}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
