import type { SystemBundle } from '../types/bundle'

export const systemSelectors = {
  snapshot: (b: SystemBundle) => b.snapshot,
  assets: (b: SystemBundle) => b.snapshot.assets,
  portfolio: (b: SystemBundle) => b.snapshot.portfolio,
  engineStatus: (b: SystemBundle) => b.snapshot.engine_status,
  health: (b: SystemBundle) => b.live.health,
  mt5: (b: SystemBundle) => b.live.mt5,
}
