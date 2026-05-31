import { createApiQuery } from '../lib/api'
import { HealthResponseSchema } from '../lib/schemas'
import { useMarketClosed } from './useMarketClosed'
import type { z } from 'zod'

export type HealthComponent = z.infer<typeof HealthResponseSchema>['assets'][string]['components']
export type AssetHealth = z.infer<typeof HealthResponseSchema>['assets'][string]
export type SystemHealth = z.infer<typeof HealthResponseSchema>['system_health']
export type HealthResponse = z.infer<typeof HealthResponseSchema>

const useHealthScoresQuery = createApiQuery<HealthResponse>('/health.json', HealthResponseSchema)

export function useHealthScores() {
  const closed = useMarketClosed()
  return useHealthScoresQuery({
    refetchInterval: closed ? 300_000 : 60_000,
    staleTime: closed ? 290_000 : 50_000,
  })
}
