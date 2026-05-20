import { useQuery } from '@tanstack/react-query'
import type { EngineSnapshot } from '../types/portfolio'

async function fetchState(): Promise<EngineSnapshot> {
  const res = await fetch('/state.json')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export function usePortfolioState() {
  return useQuery({
    queryKey: ['portfolioState'],
    queryFn: fetchState,
    refetchInterval: 30_000,
    staleTime: 25_000,
  })
}
