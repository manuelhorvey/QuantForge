import { useQuery } from '@tanstack/react-query'
import type { TradeEntry } from '../types/trades'

async function fetchTrades(params: { limit?: number; offset?: number } = {}): Promise<TradeEntry[]> {
  const qs = new URLSearchParams()
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.offset) qs.set('offset', String(params.offset))
  const res = await fetch(`/trades.json?${qs}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export function useTrades(limit = 10, offset = 0) {
  return useQuery({
    queryKey: ['trades', limit, offset],
    queryFn: () => fetchTrades({ limit, offset }),
    refetchInterval: 60_000,
    staleTime: 50_000,
  })
}
