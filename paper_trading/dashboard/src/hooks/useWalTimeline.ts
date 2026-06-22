import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '../lib/api'

export interface WalEvent {
  sequence: number
  timestamp: string
  event_type: 'features_snapshot' | 'inference_output' | 'decision_output'
  payload: Record<string, unknown>
}

interface WalResponse {
  events: WalEvent[]
  total: number
  asset: string
}

export function useWalTimeline(assetName: string) {
  return useQuery({
    queryKey: ['walTimeline', assetName],
    queryFn: () => fetchApi<WalResponse>(`/wal/${assetName}.json`),
    refetchInterval: 30_000,
    staleTime: 10_000,
    enabled: !!assetName,
  })
}

export function groupWalEvents(events: WalEvent[]) {
  const groups: { featureHash: string; ts: string; seq: number; events: WalEvent[] }[] = []
  const map = new Map<string, WalEvent[]>()

  for (const ev of events) {
    const fh = ev.payload?.feature_hash as string | undefined
    if (!fh) continue
    const list = map.get(fh) ?? []
    list.push(ev)
    map.set(fh, list)
  }

  for (const [fh, list] of map) {
    const sorted = list.sort((a, b) => a.sequence - b.sequence)
    groups.push({
      featureHash: fh,
      ts: sorted[0].timestamp ?? '',
      seq: sorted[0].sequence,
      events: sorted,
    })
  }

  groups.sort((a, b) => b.seq - a.seq)
  return groups
}