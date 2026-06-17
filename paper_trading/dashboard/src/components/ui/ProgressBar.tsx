interface ProgressBarProps {
  value: number
  max?: number
  color?: string
  className?: string
  barClassName?: string
  height?: string
  showLabel?: boolean
  label?: string
}

function resolveColor(v: number, max: number): string {
  const pct = (v / max) * 100
  if (pct >= 80) return 'bg-gov-green'
  if (pct >= 50) return 'bg-gov-yellow'
  return 'bg-gov-red'
}

export default function ProgressBar({
  value,
  max = 100,
  color,
  className = '',
  barClassName = '',
  height = 'h-1.5',
  showLabel = false,
  label,
}: ProgressBarProps) {
  const pct = Math.min(Math.max((value / max) * 100, 0), 100)
  const barColor = color ?? resolveColor(value, max)

  return (
    <div className={className}>
      {showLabel && (
        <div className="flex items-center justify-between mb-1">
          {label && <span className="text-2xs text-tertiary font-medium">{label}</span>}
          <span className="text-2xs font-mono tabular-nums text-tertiary">{pct.toFixed(0)}%</span>
        </div>
      )}
      <div className={`w-full ${height} bg-panel rounded-full overflow-hidden`}>
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor} ${barClassName}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}
