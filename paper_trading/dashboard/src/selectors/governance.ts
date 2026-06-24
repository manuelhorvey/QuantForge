import type { AssetState, EngineSnapshot } from '../types/portfolio'

export interface GovernanceState {
  name: string
  validityState: string
  halted: boolean
  haltReasons: string[]
  softWarnings: string[]
  narrativeRegime: string | null
  narrativeStale: boolean
  liquidityRegime: string
  slMult: number
  sizeScalar: number
  floorActive: boolean
}

const MIN_SIZE_FLOOR = 0.30

function extractAssetGovernance(name: string, asset: AssetState): GovernanceState {
  const geom = asset.regime_geometry?.[asset.validity_state] ?? { sl_mult: 1.0, tp_mult: 1.0 }
  const regimeSl = geom.sl_mult
  const regimeSize = geom.tp_mult

  const combinedSl = regimeSl * (asset.narrative_sl_mult ?? 1.0) * (asset.liquidity_sl_mult ?? 1.0)
  const rawSize = regimeSize * (asset.narrative_size_scalar ?? 1.0) * (asset.liquidity_size_scalar ?? 1.0)
  const combinedSize = Math.max(rawSize, MIN_SIZE_FLOOR)

  return {
    name,
    validityState: asset.validity_state,
    halted: asset.halt?.halted ?? false,
    haltReasons: asset.halt?.reasons ?? [],
    softWarnings: asset.soft_warnings ?? [],
    narrativeRegime: asset.narrative_regime,
    narrativeStale: asset.narrative_stale ?? false,
    liquidityRegime: asset.liquidity_regime,
    slMult: Math.min(combinedSl, 10.0),
    sizeScalar: combinedSize,
    floorActive: combinedSize === MIN_SIZE_FLOOR,
  }
}

export function selectGovernance(snapshot: EngineSnapshot): GovernanceState[] {
  const assets = snapshot.assets ?? {}
  return Object.entries(assets)
    .map(([name, asset]) => extractAssetGovernance(name, asset))
    .sort((a, b) => a.name.localeCompare(b.name))
}

export function selectGovernanceByAsset(
  snapshot: EngineSnapshot,
  assetName: string,
): GovernanceState | undefined {
  const asset = snapshot.assets?.[assetName]
  if (!asset) return undefined
  return extractAssetGovernance(assetName, asset)
}

export function selectGovernanceSummary(snapshot: EngineSnapshot): {
  total: number
  halted: number
  healthy: number
  floorActive: number
} {
  const states = selectGovernance(snapshot)
  return {
    total: states.length,
    halted: states.filter(s => s.halted).length,
    healthy: states.filter(s => s.validityState === 'GREEN' || s.validityState === 'YELLOW').length,
    floorActive: states.filter(s => s.floorActive).length,
  }
}
