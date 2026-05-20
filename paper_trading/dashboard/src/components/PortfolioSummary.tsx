import { useMemo } from 'react'
import { usePortfolioState } from '../hooks/usePortfolioState'

export default function PortfolioSummary() {
  const { data, isPending, isError } = usePortfolioState()
  const p = data?.portfolio

  if (isPending) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card-gradient card-border rounded-xl p-4 animate-pulse">
            <div className="h-3 bg-gray-800 rounded w-1/3 mb-3" />
            <div className="h-7 bg-gray-800 rounded w-2/3 mb-2" />
            <div className="h-3 bg-gray-800/50 rounded w-1/2" />
          </div>
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="card-gradient card-border rounded-xl p-6">
        <div className="flex items-center gap-3 text-sm text-tertiary">
          <svg className="w-4 h-4 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <span>Connecting to paper trading engine...</span>
        </div>
      </div>
    )
  }

  const cards = useMemo(() => {
    if (!p) return []
    return [
      {
        label: 'Portfolio Value',
        value: `$${(p.total_value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        sub: `Capital: $${(p.capital ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
        color: 'text-emerald-400',
        accent: 'bg-emerald-500/20',
      },
      {
        label: 'Total Return',
        value: `${(p.total_return ?? 0).toFixed(2)}%`,
        sub: `Unrealized: $${(p.unrealized_pnl ?? 0).toFixed(2)}`,
        color: (p.total_return ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400',
        accent: (p.total_return ?? 0) >= 0 ? 'bg-emerald-500/20' : 'bg-red-500/20',
      },
      {
        label: 'Realized P&L',
        value: `${(p.realized_return ?? 0) >= 0 ? '+' : ''}${(p.realized_return ?? 0).toFixed(2)}%`,
        sub: `Realized: $${(p.realized_value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
        color: (p.realized_return ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400',
        accent: (p.realized_return ?? 0) >= 0 ? 'bg-emerald-500/20' : 'bg-red-500/20',
      },
      {
        label: 'Positions',
        value: `${p.open_positions ?? 0} / ${p.closed_trades ?? 0}`,
        sub: `Open / Closed`,
        color: 'text-blue-400',
        accent: 'bg-blue-500/20',
      },
    ]
  }, [p])

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map(c => (
        <div key={c.label} className="relative card-gradient card-border rounded-xl p-4 hover-lift overflow-hidden group">
          <div className="relative z-10">
            <div className="flex items-center gap-2 mb-2">
              <div className={`w-1.5 h-1.5 rounded-full ${c.accent}`} />
              <span className="text-[11px] text-tertiary font-medium tracking-wide">{c.label}</span>
            </div>
            <div className={`text-2xl font-bold tracking-tight metric-value ${c.color}`}>{c.value}</div>
            <div className="text-[11px] text-tertiary mt-1.5 font-mono">{c.sub}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
