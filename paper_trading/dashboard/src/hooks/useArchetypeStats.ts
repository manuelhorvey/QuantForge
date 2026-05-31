import { createApiQuery } from '../lib/api'

export interface ArchetypeStats {
  by_archetype: Record<string, {
    n: number
    avg_r: number
    win_rate: number
    tp_rate: number
    sl_rate: number
    avg_mae: number
    avg_mfe: number
    avg_entry_slippage_bps: number
    avg_bars_held: number
  }>
}

const useArchetypeStatsQuery = createApiQuery<ArchetypeStats>('/archetype/stats.json')

export function useArchetypeStats() {
  return useArchetypeStatsQuery({ refetchInterval: 120_000, staleTime: 100_000 })
}
