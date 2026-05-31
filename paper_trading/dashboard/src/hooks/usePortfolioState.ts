import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '../lib/api'
import type { EngineSnapshot } from '../types/portfolio'

export function usePortfolioState() {
  return useQuery({
    queryKey: ['portfolioState'],
    queryFn: async () => {
      const json = await fetchApi<unknown>('/state.json')
      if (typeof json !== 'object' || json === null || !('assets' in json) || typeof (json as Record<string, unknown>).assets !== 'object') {
        console.error('[State] top-level validation failed: missing assets or invalid shape')
        throw new Error('Invalid state data from server')
      }
      return json as EngineSnapshot
    },
    refetchInterval: (q) => {
      const d = q.state.data
      return d?.engine_status?.market_closed ? 120_000 : 30_000
    },
    staleTime: (q) => {
      const d = q.state.data
      return d?.engine_status?.market_closed ? 110_000 : 25_000
    },
  })
}
