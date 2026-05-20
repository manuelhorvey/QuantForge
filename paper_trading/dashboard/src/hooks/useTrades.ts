import { useQuery } from '@tanstack/react-query'
import type { TradeEntry } from '../types/trades'

async function fetchTrades(): Promise<TradeEntry[]> {
  const res = await fetch('/trades.json')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export function useTrades() {
  return useQuery({
    queryKey: ['trades'],
    queryFn: fetchTrades,
    refetchInterval: 60_000,
    staleTime: 50_000,
  })
}
