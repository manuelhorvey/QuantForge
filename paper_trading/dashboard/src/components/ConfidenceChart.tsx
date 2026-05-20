import { useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { useQuery } from '@tanstack/react-query'

async function fetchConfidence(): Promise<{ live: Record<string, Record<string, number>>; historical: Record<string, number>[] }> {
  const res = await fetch('/confidence.json')
  if (!res.ok) return { live: {}, historical: [] }
  return res.json()
}

function aggregateBuckets(live: Record<string, Record<string, number>>): { range: string; count: number }[] {
  const agg: Record<string, number> = {}
  for (const assetBuckets of Object.values(live)) {
    for (const [range, count] of Object.entries(assetBuckets)) {
      agg[range] = (agg[range] ?? 0) + count
    }
  }
  return Object.entries(agg)
    .sort(([a], [b]) => parseInt(a) - parseInt(b))
    .map(([range, count]) => ({ range, count }))
}

export default function ConfidenceChart() {
  const { data: apiData, isPending } = useQuery({
    queryKey: ['confidenceDistribution'],
    queryFn: fetchConfidence,
    refetchInterval: 60_000,
    staleTime: 50_000,
  })

  const liveBuckets = useMemo(() => {
    if (!apiData?.live) return []
    return aggregateBuckets(apiData.live)
  }, [apiData])

  const historicalCount = useMemo(() => {
    if (!apiData?.historical || apiData.historical.length === 0) return null
    const agg: Record<string, number> = {}
    for (const entry of apiData.historical) {
      for (const [range, count] of Object.entries(entry)) {
        if (range === 'date') continue
        agg[range] = (agg[range] ?? 0) + (count as number)
      }
    }
    const total = Object.values(agg).reduce((s, v) => s + v, 0)
    return { buckets: agg, total }
  }, [apiData])

  const showHistorical = historicalCount && historicalCount.total > 0

  return (
    <div className="card-gradient card-border rounded-xl p-4">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-2 h-2 rounded-full bg-emerald-500/50" />
        <h2 className="text-sm font-semibold text-primary">Confidence Distribution</h2>
      </div>
      {isPending ? (
        <div className="text-xs text-tertiary text-center py-8 animate-pulse">Loading...</div>
      ) : liveBuckets.length === 0 && !showHistorical ? (
        <div className="text-xs text-tertiary text-center py-8">No signal data yet</div>
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={liveBuckets} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-panel)" />
              <XAxis dataKey="range" tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }} axisLine={{ stroke: 'var(--color-border)' }} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--color-text-tertiary)' }} allowDecimals={false} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{
                  background: 'var(--color-card)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '8px',
                  fontSize: '12px',
                  boxShadow: 'var(--shadow-lift)',
                }}
                labelStyle={{ color: 'var(--color-text-tertiary)' }}
              />
              <Bar dataKey="count" fill="#34d399" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
      {showHistorical && (
        <div className="mt-3 pt-3 border-t border-default">
          <div className="text-[10px] text-tertiary mb-2">Historical: {historicalCount.total} signals across {Object.keys(historicalCount.buckets).length} buckets</div>
          <div className="flex gap-1 h-6">
            {Object.entries(historicalCount.buckets)
              .sort(([a], [b]) => parseInt(a) - parseInt(b))
              .map(([range, count]) => (
                <div
                  key={range}
                  className="flex-1 rounded-sm bg-emerald-500/20 relative overflow-hidden"
                  title={`${range}: ${count} signals`}
                >
                  <div
                    className="absolute bottom-0 left-0 right-0 bg-emerald-500/40 rounded-sm transition-all"
                    style={{ height: `${(count / historicalCount.total) * 100}%` }}
                  />
                </div>
              ))}
          </div>
          <div className="flex justify-between text-[9px] text-tertiary mt-1">
            {Object.entries(historicalCount.buckets)
              .sort(([a], [b]) => parseInt(a) - parseInt(b))
              .map(([range]) => (
                <span key={range}>{range}</span>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
