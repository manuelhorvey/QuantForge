import { useMemo } from 'react'
import { usePortfolioState } from './usePortfolioState'
import type { ExitReasons } from '../types/portfolio'

export interface AssetOutcome {
  asset: string
  n_trades: number
  tp_rate: number
  sl_rate: number
  signal_flip_rate: number
  avg_r: number
  win_rate: number
  profit_factor: number | null
}

export interface TradeOutcomesData {
  overall: ExitReasons & { win_rate: number; profit_factor: number | null }
  by_asset: AssetOutcome[]
}

export function useTradeOutcomes() {
  const { data, isPending, isError } = usePortfolioState()

  const outcomes = useMemo<TradeOutcomesData | null>(() => {
    if (!data?.assets) return null

    const assets = Object.values(data.assets)
    const byAsset: AssetOutcome[] = assets
      .filter((a) => a.metrics.n_trades > 0)
      .map((a) => {
        const m = a.metrics
        const er = m.exit_reasons
        return {
          asset: m.asset,
          n_trades: m.n_trades,
          tp_rate: er?.tp_rate ?? 0,
          sl_rate: er?.sl_rate ?? 0,
          signal_flip_rate: er?.signal_flip_rate ?? 0,
          avg_r: er?.avg_r ?? 0,
          win_rate: m.win_rate,
          profit_factor: m.profit_factor,
        }
      })

    // Derive overall from trade_logs across all assets
    let totalTP = 0
    let totalSL = 0
    let totalFlip = 0
    let totalTrades = 0
    let totalR = 0
    let totalWins = 0
    let totalProfit = 0
    let totalLoss = 0

    for (const a of assets) {
      const tl = a.metrics.trade_log
      if (!tl) continue
      for (const t of tl) {
        totalTrades++
        if (t.reason === 'tp') totalTP++
        else if (t.reason === 'sl') totalSL++
        else if (t.reason === 'signal_flip') totalFlip++
        if (t.return > 0) totalWins++
        totalProfit += Math.max(0, t.return)
        totalLoss += Math.max(0, -t.return)
      }
      totalR += (a.metrics.exit_reasons?.avg_r ?? 0) * (a.metrics.n_trades ?? 0)
    }

    return {
      overall: {
        tp_rate: totalTrades > 0 ? totalTP / totalTrades : 0,
        sl_rate: totalTrades > 0 ? totalSL / totalTrades : 0,
        signal_flip_rate: totalTrades > 0 ? totalFlip / totalTrades : 0,
        avg_r: totalTrades > 0 ? totalR / totalTrades : 0,
        win_rate: totalTrades > 0 ? totalWins / totalTrades : 0,
        profit_factor: totalLoss > 0 ? totalProfit / totalLoss : null,
      },
      by_asset: byAsset,
    }
  }, [data])

  return { outcomes, isPending, isError }
}
