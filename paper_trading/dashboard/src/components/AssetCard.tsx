import React, { useMemo } from 'react'
import { usePortfolioState } from '../hooks/usePortfolioState'

interface Props {
  name: string
}

const SIGNAL_COLORS: Record<string, string> = {
  BUY: 'bg-emerald-950 text-emerald-400 border-emerald-800',
  SELL: 'bg-red-950 text-red-400 border-red-800',
  FLAT: 'bg-amber-950 text-amber-400 border-amber-800',
}

const SIGNAL_BG: Record<string, string> = {
  BUY: 'bg-emerald-500',
  SELL: 'bg-red-500',
  FLAT: 'bg-amber-500',
}

function confidenceColor(c: number): string {
  if (c >= 60) return 'bg-emerald-500'
  if (c >= 45) return 'bg-amber-500'
  return 'bg-red-500'
}

const AssetCard: React.FC<Props> = React.memo(({ name }) => {
  const { data } = usePortfolioState()
  const asset = data?.assets?.[name]

  const info = useMemo(() => {
    if (!asset) return null
    const m = asset.metrics
    const sig = asset.last_signal
    const pos = m.position
    const signalClass = SIGNAL_COLORS[sig?.signal] ?? SIGNAL_COLORS.FLAT
    const confColor = confidenceColor(sig?.confidence ?? 0)
    return {
      signal: sig?.signal ?? 'FLAT',
      confidence: sig?.confidence ?? 0,
      price: sig?.close_price,
      signalClass,
      confColor,
      totalReturn: m.mtm_return ?? m.total_return ?? 0,
      drawdown: m.drawdown ?? 0,
      meanConf: m.mean_confidence ?? 0,
      nTrades: m.n_trades ?? 0,
      nSignals: m.n_signals ?? 0,
      pos,
      dist: m.signal_distribution,
      currentValue: m.current_value ?? 0,
    }
  }, [asset])

  if (!info) {
    return (
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
        <div className="text-sm text-gray-500">{name}</div>
        <div className="text-xs text-gray-400 mt-2">No data</div>
      </div>
    )
  }

  return (
    <div className={`bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 hover:border-gray-400 dark:hover:border-gray-600 transition-colors`}>
      <div className="flex items-center justify-between mb-3">
        <span className="font-semibold text-sm">{name}</span>
        {info.price != null && (
          <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">
            ${info.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 })}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2 mb-3">
        <span className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${info.signalClass}`}>
          {info.signal}
        </span>
        <div className="flex-1 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${info.confColor}`} style={{ width: `${Math.min(info.confidence, 100)}%` }} />
        </div>
        <span className="text-xs text-gray-400 dark:text-gray-500 font-mono w-10 text-right">
          {info.confidence.toFixed(1)}%
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <span className="text-gray-400 dark:text-gray-500">Return</span>
          <div className={`font-mono ${info.totalReturn >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {info.totalReturn >= 0 ? '+' : ''}{info.totalReturn.toFixed(2)}%
          </div>
        </div>
        <div>
          <span className="text-gray-400 dark:text-gray-500">DD</span>
          <div className={`font-mono ${info.drawdown > -3 ? 'text-emerald-400' : info.drawdown > -5 ? 'text-amber-400' : 'text-red-400'}`}>
            {info.drawdown.toFixed(2)}%
          </div>
        </div>
        <div>
          <span className="text-gray-400 dark:text-gray-500">Conf</span>
          <div className="font-mono text-gray-50 dark:text-gray-900">{info.meanConf.toFixed(1)}%</div>
        </div>
      </div>

      {info.pos && (
        <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-800 text-[11px] text-gray-400 dark:text-gray-500 flex justify-between">
          <span>{info.pos.side.toUpperCase()} @ ${info.pos.entry.toFixed(2)}</span>
          {info.pos.unrealized_pnl != null && (
            <span className={info.pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
              {info.pos.unrealized_pnl >= 0 ? '+' : ''}{info.pos.unrealized_pnl.toFixed(2)}%
            </span>
          )}
        </div>
      )}

      {info.dist && (
        <div className="mt-2 flex gap-2 text-[10px] text-gray-400 dark:text-gray-500">
          <span>{info.dist.BUY ?? 0}B</span>
          <span>{info.dist.SELL ?? 0}S</span>
          <span>{info.dist.FLAT ?? 0}F</span>
          <span className="ml-auto">{info.nSignals} sigs</span>
        </div>
      )}
    </div>
  )
})

AssetCard.displayName = 'AssetCard'
export default AssetCard
