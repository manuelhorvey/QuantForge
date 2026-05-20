import { useMemo } from 'react'
import { usePortfolioState } from '../hooks/usePortfolioState'

export default function PortfolioSummary() {
  const { data } = usePortfolioState()
  const p = data?.portfolio

  const cards = useMemo(() => {
    if (!p) return []
    return [
      {
        label: 'Portfolio Value',
        value: `$${(p.total_value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
        sub: `Capital: $${(p.capital ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
        color: 'text-emerald-400',
      },
      {
        label: 'Total Return',
        value: `${(p.total_return ?? 0).toFixed(2)}%`,
        sub: `Unrealized: $${(p.unrealized_pnl ?? 0).toFixed(2)}`,
        color: (p.total_return ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400',
      },
      {
        label: 'Realized P&L',
        value: `${(p.realized_return ?? 0) >= 0 ? '+' : ''}${(p.realized_return ?? 0).toFixed(2)}%`,
        sub: `Realized: $${(p.realized_value ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
        color: (p.realized_return ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400',
      },
      {
        label: 'Positions',
        value: `${p.open_positions ?? 0} / ${p.closed_trades ?? 0}`,
        sub: `Open / Closed`,
        color: 'text-gray-50 dark:text-gray-900',
      },
    ]
  }, [p])

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map(c => (
        <div key={c.label} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div className="text-xs text-gray-400 dark:text-gray-500 mb-1">{c.label}</div>
          <div className={`text-2xl font-bold ${c.color}`}>{c.value}</div>
          <div className="text-xs text-gray-500 mt-1">{c.sub}</div>
        </div>
      ))}
    </div>
  )
}
