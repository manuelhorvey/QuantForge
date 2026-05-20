import { useHaltStatus } from '../hooks/useHaltStatus'
import { usePortfolioState } from '../hooks/usePortfolioState'

export default function HaltConditions() {
  const { data } = usePortfolioState()
  const status = useHaltStatus(data)
  if (!data) return null

  const cards = [
    {
      label: 'Max Drawdown',
      value: `${status.maxDrawdown.toFixed(2)}%`,
      threshold: `${status.drawdownTrigger.toFixed(0)}%`,
      pass: status.drawdownPass,
    },
    {
      label: 'Monthly PF',
      value: status.minMonthlyPf === Infinity || isNaN(status.minMonthlyPf) ? '—' : status.minMonthlyPf.toFixed(2),
      threshold: status.monthlyPfTrigger.toFixed(2),
      pass: status.monthlyPfPass,
    },
    {
      label: 'Signal Drought',
      value: '0d',
      threshold: `${data.halt_conditions?.signal_drought ?? 30}d`,
      pass: true,
    },
    {
      label: 'Prob Drift',
      value: `< ${((data.halt_conditions?.prob_drift ?? 0.15) * 100).toFixed(0)}%`,
      threshold: `${((data.halt_conditions?.prob_drift ?? 0.15) * 100).toFixed(0)}%`,
      pass: true,
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map(c => (
        <div key={c.label} className={`border rounded-xl p-4 ${
          c.pass
            ? 'bg-emerald-950/10 border-emerald-800/30'
            : 'bg-red-950/10 border-red-800/30'
        }`}>
          <div className="text-xs text-gray-400 dark:text-gray-500 mb-1">{c.label}</div>
          <div className={`text-lg font-bold ${c.pass ? 'text-emerald-400' : 'text-red-400'}`}>
            {c.value}
          </div>
          <div className="text-[11px] text-gray-500 mt-0.5">
            {c.pass ? '✓' : '✗'} {c.threshold}
          </div>
        </div>
      ))}
    </div>
  )
}
