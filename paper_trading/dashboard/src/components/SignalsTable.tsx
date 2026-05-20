import { useMemo } from 'react'
import { usePortfolioState } from '../hooks/usePortfolioState'

export default function SignalsTable() {
  const { data } = usePortfolioState()
  const rows = useMemo(() => {
    if (!data?.assets) return []
    return Object.entries(data.assets)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, asset]) => {
        const sig = asset.last_signal
        const m = asset.metrics
        const alloc = data.portfolio?.allocations?.[name] ?? 0
        return { name, sig, m, alloc }
      })
  }, [data])

  if (rows.length === 0) return null

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
      <h2 className="text-sm font-semibold mb-3">Signals</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-800">
              <th className="text-left py-2 pr-3">Asset</th>
              <th className="text-left py-2 pr-3">Direction</th>
              <th className="text-left py-2 pr-3">Signal</th>
              <th className="text-right py-2 pr-3">Conf</th>
              <th className="text-right py-2 pr-3">Price</th>
              <th className="text-right py-2 pr-3">Alloc</th>
              <th className="text-right py-2 pr-3">Return</th>
              <th className="text-right py-2">DD</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ name, sig, m, alloc }) => (
              <tr key={name} className="border-b border-gray-100 dark:border-gray-800/50 hover:bg-gray-50 dark:hover:bg-gray-800/30">
                <td className="py-2 pr-3 font-medium">{name}</td>
                <td className="py-2 pr-3 text-gray-400 dark:text-gray-500">
                  {sig?.signal === 'BUY' ? 'Bullish' : sig?.signal === 'SELL' ? 'Bearish' : 'Neutral'}
                </td>
                <td className={`py-2 pr-3 font-medium ${
                  sig?.signal === 'BUY' ? 'text-emerald-400' : sig?.signal === 'SELL' ? 'text-red-400' : 'text-amber-400'
                }`}>
                  {sig?.signal ?? 'FLAT'}
                </td>
                <td className="py-2 pr-3 text-right font-mono">
                  <span className="inline-block w-12 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden align-middle mr-1.5">
                    <span className={`block h-full rounded-full ${
                      (sig?.confidence ?? 0) >= 60 ? 'bg-emerald-500' : (sig?.confidence ?? 0) >= 45 ? 'bg-amber-500' : 'bg-red-500'
                    }`} style={{ width: `${Math.min(sig?.confidence ?? 0, 100)}%` }} />
                  </span>
                  {(sig?.confidence ?? 0).toFixed(1)}%
                </td>
                <td className="py-2 pr-3 text-right font-mono">
                  ${sig?.close_price?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 }) ?? '—'}
                </td>
                <td className="py-2 pr-3 text-right font-mono">{(alloc * 100).toFixed(0)}%</td>
                <td className={`py-2 pr-3 text-right font-mono ${(m?.mtm_return ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {(m?.mtm_return ?? 0).toFixed(2)}%
                </td>
                <td className={`py-2 text-right font-mono ${
                  (m?.drawdown ?? 0) > -3 ? 'text-emerald-400' : (m?.drawdown ?? 0) > -5 ? 'text-amber-400' : 'text-red-400'
                }`}>
                  {(m?.drawdown ?? 0).toFixed(2)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
