import { createApiQuery } from '../lib/api'
import type { ExecutionQualityResponse } from '../types/execution'

const useExecutionQualityQuery = createApiQuery<ExecutionQualityResponse>('/execution/quality.json')

export function useExecutionQuality() {
  return useExecutionQualityQuery({ refetchInterval: 60_000, staleTime: 50_000 })
}
