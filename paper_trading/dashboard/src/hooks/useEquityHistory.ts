import { z } from 'zod'
import { createApiQuery } from '../lib/api'
import { EquityHistoryPointSchema } from '../lib/schemas'
import { useMarketClosed } from './useMarketClosed'

export type EquityHistoryPoint = z.infer<typeof EquityHistoryPointSchema>

const useEquityHistoryQuery = createApiQuery<EquityHistoryPoint[]>('/equity_history.json', z.array(EquityHistoryPointSchema))

export function useEquityHistory() {
  const closed = useMarketClosed()
  return useEquityHistoryQuery({
    refetchInterval: closed ? 300_000 : 60_000,
    staleTime: closed ? 290_000 : 50_000,
  })
}
