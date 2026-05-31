import { createApiQuery } from '../lib/api'
import type { AttributionSummary } from '../types/attribution'

const useAttributionSummaryQuery = createApiQuery<AttributionSummary>('/attribution/summary.json')

export function useAttributionSummary() {
  return useAttributionSummaryQuery({ refetchInterval: 60_000, staleTime: 50_000 })
}
