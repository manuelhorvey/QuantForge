import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '../lib/api'
import type { ShadowTradeRecord } from '../types/shadow'

async function fetchShadowTrades(limit: number, offset: number, alt_label?: string): Promise<ShadowTradeRecord[]> {
  const qs = new URLSearchParams()
  qs.set('limit', String(limit))
  qs.set('offset', String(offset))
  if (alt_label) qs.set('alt_label', alt_label)
  return fetchApi<ShadowTradeRecord[]>(`/shadow/trades.json?${qs}`)
}

export function useShadowTrades(limit = 20, offset = 0, alt_label?: string) {
  return useQuery({
    queryKey: ['shadowTrades', limit, offset, alt_label],
    queryFn: () => fetchShadowTrades(limit, offset, alt_label),
    refetchInterval: 60_000,
    staleTime: 50_000,
  })
}
