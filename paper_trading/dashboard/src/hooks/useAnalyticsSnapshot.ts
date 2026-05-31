import { createApiQuery } from '../lib/api'

export interface AnalyticsSnapshot {
  overall: {
    n_trades: number
    avg_r: number
    win_rate: number
    tp_rate: number
    sl_rate: number
  }
  by_archetype: Record<string, {
    n: number
    avg_r: number
    win_rate: number
    tp_rate: number
    sl_rate: number
    avg_entry_slippage: number
    avg_mae: number
    avg_mfe: number
  }>
  by_regime: Record<string, {
    n: number
    avg_r: number
    win_rate: number
  }>
  shadow: {
    n: number
    divergence_rate: number
    avg_r_delta: number
  }
}

const useAnalyticsSnapshotQuery = createApiQuery<AnalyticsSnapshot>('/analytics/snapshot.json')

export function useAnalyticsSnapshot() {
  return useAnalyticsSnapshotQuery({ refetchInterval: 30_000, staleTime: 25_000 })
}
