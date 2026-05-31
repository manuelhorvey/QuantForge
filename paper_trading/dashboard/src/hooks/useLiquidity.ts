import { createApiQuery } from '../lib/api'
import { LiquidityDataSchema } from '../lib/schemas'
import type { z } from 'zod'

export type LiquidityData = z.infer<typeof LiquidityDataSchema>
export type LiquidityStatus = LiquidityData[string]

const useLiquidityQuery = createApiQuery<LiquidityData>('/liquidity.json', LiquidityDataSchema)

export function useLiquidity() {
  return useLiquidityQuery({ refetchInterval: 60_000, staleTime: 60_000, gcTime: 300_000 })
}
