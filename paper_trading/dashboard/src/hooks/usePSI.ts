import { createApiQuery } from '../lib/api'
import { PSIDataSchema } from '../lib/schemas'
import type { z } from 'zod'

export type PSIFeatureEntry = z.infer<typeof PSIDataSchema>[string]['per_feature'][number]
export type PSIAssetStatus = z.infer<typeof PSIDataSchema>[string]
export type PSIData = z.infer<typeof PSIDataSchema>

const usePSIQuery = createApiQuery<PSIData>('/psi.json', PSIDataSchema)

export function usePSI() {
  return usePSIQuery({ refetchInterval: 60_000, staleTime: 60_000, gcTime: 300_000 })
}
