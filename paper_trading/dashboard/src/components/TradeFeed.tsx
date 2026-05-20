import { useMemo } from 'react'
import { useTrades } from '../hooks/useTrades'

export default function TradeFeed() {
  const { data: trades, isPending } = useTrades()
  const rows = useMemo(() => trades ?? [], [trades])

  if (isPending) {
    return (
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 animate-pulse">
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/4 mb-3" />
        <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded mb-2" />
        <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded mb-2" />
        <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded" />
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
        <h2 className="text-sm font-semibold mb-3">Recent Trades</h2>
        <div className="text-xs text-gray-400 dark:text-gray-500 text-center py-6">No trades closed yet</div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold">Recent Trades</h2>
        <span className="text-xs text-gray-400 dark:text-gray-500">{rows.length} trades</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-800">
              <th className="text-left py-2 pr-3">Date</th>
              <th className="text-left py-2 pr-3">Asset</th>
              <th className="text-left py-2 pr-3">Side</th>
              <th className="text-right py-2 pr-3">Entry</th>
              <th className="text-right py-2 pr-3">Exit</th>
              <th className="text-right py-2 pr-3">Return</th>
              <th className="text-right py-2 pr-3">Bars</th>
              <th className="text-right py-2">Reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t, i) => {
              const ret = (t.return ?? 0) * 100
              return (
                <tr key={i} className="border-b border-gray-100 dark:border-gray-800/50 hover:bg-gray-50 dark:hover:bg-gray-800/30">
                  <td className="py-2 pr-3 text-gray-400 dark:text-gray-500 font-mono">{t.exit_date?.split(' ')[0] ?? '—'}</td>
                  <td className="py-2 pr-3 font-medium">{t.asset ?? '—'}</td>
                  <td className={`py-2 pr-3 font-medium ${t.side === 'LONG' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {t.side ?? '—'}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono">${t.entry?.toFixed(2) ?? '—'}</td>
                  <td className="py-2 pr-3 text-right font-mono">${t.exit?.toFixed(2) ?? '—'}</td>
                  <td className={`py-2 pr-3 text-right font-mono ${ret >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {ret >= 0 ? '+' : ''}{ret.toFixed(2)}%
                  </td>
                  <td className="py-2 pr-3 text-right font-mono">{t.bars != null ? `${t.bars}d` : '—'}</td>
                  <td className={`py-2 text-right font-mono ${
                    t.reason === 'TP' ? 'text-emerald-400' : t.reason === 'SL' ? 'text-red-400' : 'text-amber-400'
                  }`}>
                    {t.reason ?? '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
