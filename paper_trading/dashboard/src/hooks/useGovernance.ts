import { createApiQuery } from '../lib/api'
import { GovernanceDataSchema } from '../lib/schemas'
import type { z } from 'zod'

export type GovernanceState = z.infer<typeof GovernanceDataSchema>[string]
export type GovernanceData = z.infer<typeof GovernanceDataSchema>

const useGovernanceQuery = createApiQuery<GovernanceData>('/governance.json', GovernanceDataSchema)

export function useGovernance() {
  return useGovernanceQuery({ refetchInterval: 30_000, staleTime: 25_000, gcTime: 300_000 })
}
