import { useQuery } from '@tanstack/react-query'

export interface GovernanceState {
  regime_sl_mult: number
  regime_size_scalar: number
  narrative_sl_mult: number
  narrative_size_scalar: number
  liquidity_sl_mult: number
  liquidity_size_scalar: number
  combined_sl_mult: number
  combined_size_scalar: number
  floor_active: boolean
  validity_state: string
  narrative_regime: string | null
  narrative_stale: boolean
  liquidity_regime: string
  halted: boolean
}

export interface GovernanceData {
  [asset: string]: GovernanceState
}

async function fetchGovernance(): Promise<GovernanceData> {
  const resp = await fetch('/governance.json')
  if (!resp.ok) throw new Error('Failed to fetch governance')
  return resp.json()
}

export function useGovernance() {
  return useQuery<GovernanceData>({
    queryKey: ['governance'],
    queryFn: fetchGovernance,
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}
