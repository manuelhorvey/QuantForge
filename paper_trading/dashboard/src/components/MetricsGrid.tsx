import { useMemo } from 'react'
import { usePortfolioState } from '../hooks/usePortfolioState'

export default function MetricsGrid() {
  const { data } = usePortfolioState()
  const cards = useMemo(() => {
    if (!data?.assets) return []
    return Object.entries(data.assets)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, asset]) => {
        const m = asset.metrics
        return {
          name,
          nTrades: m.n_trades ?? 0,
          profitFactor: m.profit_factor,
          winRate: m.win_rate ?? 0,
          meanConf: m.mean_confidence ?? 0,
          meanProbLong: m.mean_prob_long ?? 0,
          meanProbShort: m.mean_prob_short ?? 0,
          monthlyPf: m.monthly_pf,
          signalDist: m.signal_distribution,
        }
      })
  }, [data])

  if (cards.length === 0) return null

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {cards.map(c => (
        <div key={c.name} className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold">{c.name}</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">{c.nTrades} trades</span>
          </div>
          <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-xs">
            <div>
              <span className="text-gray-400 dark:text-gray-500">Profit Factor</span>
              <div className={`font-mono ${c.profitFactor != null && c.profitFactor >= 1 ? 'text-emerald-400' : 'text-amber-400'}`}>
                {c.profitFactor != null && !isNaN(c.profitFactor) && c.profitFactor !== Infinity ? c.profitFactor.toFixed(2) : '—'}
              </div>
            </div>
            <div>
              <span className="text-gray-400 dark:text-gray-500">Win Rate</span>
              <div className="font-mono">{c.winRate.toFixed(1)}%</div>
            </div>
            <div>
              <span className="text-gray-400 dark:text-gray-500">Mean Conf</span>
              <div className="font-mono">{c.meanConf.toFixed(1)}%</div>
            </div>
            <div>
              <span className="text-gray-400 dark:text-gray-500">P(Long/Short)</span>
              <div className="font-mono">{c.meanProbLong.toFixed(1)}% / {c.meanProbShort.toFixed(1)}%</div>
            </div>
            <div>
              <span className="text-gray-400 dark:text-gray-500">Monthly PF</span>
              <div className={`font-mono ${c.monthlyPf != null && c.monthlyPf >= 0.7 ? 'text-emerald-400' : 'text-amber-400'}`}>
                {c.monthlyPf != null && !isNaN(c.monthlyPf) && c.monthlyPf !== Infinity ? c.monthlyPf.toFixed(2) : '—'}
              </div>
            </div>
            <div>
              <span className="text-gray-400 dark:text-gray-500">Signal Dist</span>
              <div className="font-mono">
                {c.signalDist ? `${c.signalDist.BUY ?? 0}B / ${c.signalDist.SELL ?? 0}S / ${c.signalDist.FLAT ?? 0}F` : '—'}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
