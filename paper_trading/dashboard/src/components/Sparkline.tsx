interface Props {
  values: (number | null | undefined)[]
  width?: number
  height?: number
  color?: string
  className?: string
}

export default function Sparkline({ values, width = 160, height = 24, color = 'var(--color-text-muted)', className }: Props) {
  const clean = values.filter((v): v is number => v != null && !isNaN(v) && v !== Infinity && v !== -Infinity)
  if (clean.length < 2) return <svg width={width} height={height} className={className} />

  const min = Math.min(...clean)
  const max = Math.max(...clean)
  const range = max - min || 1
  const pad = 1
  const dw = width - pad * 2
  const dh = height - pad * 2

  const points = clean.map((v, i) => {
    const x = pad + (i / (clean.length - 1)) * dw
    const y = pad + (1 - (v - min) / range) * dh
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={width} height={height} className={className} viewBox={`0 0 ${width} ${height}`}>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  )
}
