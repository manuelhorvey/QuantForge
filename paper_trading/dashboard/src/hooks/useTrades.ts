import { useQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { fetchApi } from '../lib/api'
import { TradeEntrySchema } from '../lib/schemas'
import { useMarketClosed } from './useMarketClosed'

export type TradeEntry = z.infer<typeof TradeEntrySchema>

async function fetchTrades(limit: number, offset: number): Promise<TradeEntry[]> {
  const qs = new URLSearchParams()
  if (limit) qs.set('limit', String(limit))
  if (offset) qs.set('offset', String(offset))
  const json = await fetchApi<unknown>(`/trades.json?${qs}`)
  const parsed = z.array(TradeEntrySchema).safeParse(json)
  if (!parsed.success) {
    console.error('[Trades] validation failed:', parsed.error.issues)
    throw new Error('Invalid trades data from server')
  }
  return parsed.data
}

export function useTrades(limit = 10, offset = 0) {
  const closed = useMarketClosed()
  return useQuery({
    queryKey: ['trades', limit, offset],
    queryFn: () => fetchTrades(limit, offset),
    refetchInterval: closed ? 300_000 : 60_000,
    staleTime: closed ? 290_000 : 50_000,
  })
}
