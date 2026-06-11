interface Allocation {
  asset: string
  pct: number
}

interface AllocationBarProps {
  title: string
  allocations: Allocation[]
  variant?: 'current' | 'target' | 'proposed'
}

const COLORS = [
  '#2dd4bf', '#60a5fa', '#fbbf24', '#f472b6',
  '#a78bfa', '#5eead4', '#f97316', '#34d399',
  '#818cf8', '#fb7185',
]

export default function AllocationBar({ title, allocations, variant = 'current' }: AllocationBarProps) {
  const total = allocations.reduce((s, a) => s + a.pct, 0) || 1
  const borderStyle = variant === 'target'
    ? 'border-accent-emerald/30'
    : variant === 'proposed'
    ? 'border-accent-blue/30'
    : 'border-default'

  return (
    <div className={`bg-panel border ${borderStyle} rounded-lg p-3`}>
      <p className="text-2xs font-semibold text-tertiary uppercase tracking-wider mb-2">{title}</p>
      <div className="w-full h-5 bg-default rounded-full overflow-hidden flex">
        {allocations.map((alloc, i) => (
          <div
            key={alloc.asset}
            style={{
              width: `${(alloc.pct / total) * 100}%`,
              backgroundColor: COLORS[i % COLORS.length],
            }}
            className="h-full transition-all duration-300 first:rounded-l-full last:rounded-r-full"
            title={`${alloc.asset}: ${(alloc.pct * 100).toFixed(1)}%`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">
        {allocations.map((alloc, i) => (
          <div key={alloc.asset} className="flex items-center gap-1">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ backgroundColor: COLORS[i % COLORS.length] }}
            />
            <span className="text-2xs text-tertiary font-mono">{alloc.asset}</span>
            <span className="text-2xs text-secondary font-mono tabular-nums">
              {(alloc.pct * 100).toFixed(1)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
