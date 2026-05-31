import { createApiQuery } from '../lib/api'
import { RiskParityDataSchema } from '../lib/schemas'
import type { z } from 'zod'

export type RiskParityData = z.infer<typeof RiskParityDataSchema>

const useRiskParityQuery = createApiQuery<RiskParityData>('/risk-parity.json', RiskParityDataSchema)

export function useRiskParity() {
  return useRiskParityQuery({ refetchInterval: 30_000, staleTime: 15_000 })
}
