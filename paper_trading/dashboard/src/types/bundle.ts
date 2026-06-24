import type { EngineSnapshot } from './portfolio'

export interface BundleMeta {
  version: string
  server_time: string
  status: 'ok' | 'degraded' | 'partial_failure'
  snapshot_time: string
  snapshot_sequence_id: number
  max_live_age_seconds: number | null
  request_id: string
}

export interface LiveSourceMeta {
  fetch_time: string
  fetch_age_seconds: number
  is_fresh: boolean
  error?: string
}

export interface SystemBundle {
  meta: BundleMeta
  snapshot: EngineSnapshot
  live: {
    health: LiveSourceMeta & Record<string, unknown>
    mt5: LiveSourceMeta & Record<string, unknown>
  }
}
