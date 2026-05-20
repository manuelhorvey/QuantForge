import { useQuery } from '@tanstack/react-query'
import type { EquityHistoryPoint } from '../types/portfolio'

async function fetchEquityHistory(): Promise<EquityHistoryPoint[]> {
  const res = await fetch('/equity_history.json')
  if (!res.ok) return []
  return res.json()
}

export function useEquityHistory() {
  return useQuery({
    queryKey: ['equityHistory'],
    queryFn: fetchEquityHistory,
    refetchInterval: 60_000,
    staleTime: 50_000,
  })
}
