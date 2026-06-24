import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '../lib/api'
import type { SystemBundle } from '../types/bundle'

export function useSystemSnapshot() {
  return useQuery({
    queryKey: ['systemSnapshot'],
    queryFn: () => fetchApi<SystemBundle>('/state-bundle.json'),
    refetchInterval: (q) => {
      const closed = q.state.data?.snapshot?.engine_status?.market_closed
      return closed ? 30_000 : 5_000
    },
    staleTime: 3_000,
    retry: 2,
    retryDelay: 1_000,
  })
}
