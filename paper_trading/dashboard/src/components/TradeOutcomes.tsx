import { useTradeOutcomes } from '../hooks/useTradeOutcomes'

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`
}

function r2(v: number): string {
  return v.toFixed(2)
}

export default function TradeOutcomes() {
  const { outcomes, isPending, isError } = useTradeOutcomes()

  if (isPending) {
    return (
      <div className="card-gradient card-border rounded-xl p-4 animate-pulse">
        <div className="h-4 bg-gray-800 rounded w-1/3 mb-4" />
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-4 mb-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-12 bg-gray-800 rounded" />
          ))}
        </div>
        <div className="h-24 bg-gray-800 rounded" />
      </div>
    )
  }

  if (isError || !outcomes) {
    return (
      <div className="card-gradient card-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-2 h-2 rounded-full bg-red-500/50" />
          <h2 className="text-sm font-semibold text-primary">Trade Outcomes</h2>
        </div>
        <div className="text-xs text-tertiary text-center py-8">Failed to load outcome data</div>
      </div>
    )
  }

  const { overall, by_asset: byAsset } = outcomes
  const hasData = byAsset.length > 0

  return (
    <div className="card-gradient card-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-2 h-2 rounded-full bg-emerald-500/50" />
        <h2 className="text-sm font-semibold text-primary">Trade Outcomes</h2>
      </div>

      {!hasData ? (
        <div className="text-xs text-tertiary text-center py-8">No trades closed yet</div>
      ) : (
        <>
          {/* KPI row */}
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-4 mb-5">
            <KpiBox label="TP Hit Rate" value={pct(overall.tp_rate)} color="text-emerald-400" />
            <KpiBox label="SL Hit Rate" value={pct(overall.sl_rate)} color="text-red-400" />
            <KpiBox label="Flip Rate" value={pct(overall.signal_flip_rate)} color="text-amber-400" />
            <KpiBox label="Avg R" value={r2(overall.avg_r)} color={overall.avg_r >= 0 ? 'text-emerald-400' : 'text-red-400'} />
            <KpiBox label="Win Rate" value={pct(overall.win_rate)} color="text-sky-400" />
            <KpiBox label="Profit Factor" value={overall.profit_factor !== null ? r2(overall.profit_factor) : 'N/A'} color="text-violet-400" />
          </div>

          {/* Per-asset table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-tertiary border-b border-default">
                  <th className="text-left py-2 pr-3 font-medium">Asset</th>
                  <th className="text-right py-2 px-3 font-medium">Trades</th>
                  <th className="text-right py-2 px-3 font-medium">TP%</th>
                  <th className="text-right py-2 px-3 font-medium">SL%</th>
                  <th className="text-right py-2 px-3 font-medium">Flip%</th>
                  <th className="text-right py-2 px-3 font-medium">Avg R</th>
                  <th className="text-right py-2 px-3 font-medium">Win%</th>
                  <th className="text-right py-2 pl-3 font-medium">PF</th>
                </tr>
              </thead>
              <tbody>
                {byAsset.map((a) => (
                  <tr key={a.asset} className="border-b border-default/50 hover:bg-panel/50 transition-colors">
                    <td className="py-2 pr-3 font-medium text-primary">{a.asset}</td>
                    <td className="text-right py-2 px-3 text-secondary">{a.n_trades}</td>
                    <td className={`text-right py-2 px-3 ${a.tp_rate >= 0.2 ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {pct(a.tp_rate)}
                    </td>
                    <td className={`text-right py-2 px-3 ${a.sl_rate <= 0.6 ? 'text-secondary' : 'text-red-400'}`}>
                      {pct(a.sl_rate)}
                    </td>
                    <td className="text-right py-2 px-3 text-secondary">{pct(a.signal_flip_rate)}</td>
                    <td className={`text-right py-2 px-3 ${a.avg_r >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {r2(a.avg_r)}
                    </td>
                    <td className="text-right py-2 px-3 text-secondary">{pct(a.win_rate)}</td>
                    <td className="text-right py-2 pl-3 text-secondary">
                      {a.profit_factor !== null ? r2(a.profit_factor) : 'N/A'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function KpiBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-panel/50 rounded-lg p-3 text-center">
      <div className="text-[10px] text-tertiary uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-sm font-bold tabular-nums ${color}`}>{value}</div>
    </div>
  )
}
