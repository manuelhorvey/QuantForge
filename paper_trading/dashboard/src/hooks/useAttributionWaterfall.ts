import { createApiQuery } from '../lib/api'
import type { AttributionWaterfall } from '../types/attribution'

const useAttributionWaterfallQuery = createApiQuery<AttributionWaterfall>('/attribution/waterfall.json')

export function useAttributionWaterfall() {
  return useAttributionWaterfallQuery({ refetchInterval: 60_000, staleTime: 50_000 })
}
