import { createApiQuery } from '../lib/api'
import type { ShadowDivergenceSummary } from '../types/shadow'

const useShadowSummaryQuery = createApiQuery<ShadowDivergenceSummary>('/shadow/summary.json')

export function useShadowSummary() {
  return useShadowSummaryQuery({ refetchInterval: 60_000, staleTime: 50_000 })
}
