import { createApiQuery } from '../lib/api'
import type { SlippageDistribution } from '../types/execution'

const useExecutionSlippageQuery = createApiQuery<SlippageDistribution>('/execution/slippage.json')

export function useExecutionSlippage() {
  return useExecutionSlippageQuery({ refetchInterval: 60_000, staleTime: 50_000 })
}
