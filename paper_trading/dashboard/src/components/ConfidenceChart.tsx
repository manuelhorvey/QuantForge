import { useMemo, useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { usePortfolioState } from '../hooks/usePortfolioState'

interface LiveBucket {
  range: string
  count: number
}

export default function ConfidenceChart() {
  const { data } = usePortfolioState()
  const [assetFilter, setAssetFilter] = useState<string>('ALL')

  const liveBuckets = useMemo(() => {
    if (!data?.assets) return []
    const agg: Record<string, number> = {}
    for (const [name, asset] of Object.entries(data.assets)) {
      if (assetFilter !== 'ALL' && name !== assetFilter) continue
      const conf = asset.last_signal?.confidence ?? 0
      const lo = Math.floor(conf / 10) * 10
      const hi = lo + 10
      const key = `${lo}-${hi}`
      agg[key] = (agg[key] ?? 0) + 1
    }
    return Object.entries(agg)
      .sort(([a], [b]) => parseInt(a) - parseInt(b))
      .map(([range, count]) => ({ range, count }))
  }, [data, assetFilter])

  const assetNames = useMemo(() => data?.assets ? Object.keys(data.assets).sort() : [], [data])

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold">Confidence Distribution</h2>
        <select
          value={assetFilter}
          onChange={e => setAssetFilter(e.target.value)}
          className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-300"
        >
          <option value="ALL">All Assets</option>
          {assetNames.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>
      {liveBuckets.length === 0 ? (
        <div className="text-xs text-gray-400 dark:text-gray-500 text-center py-8">No signal data yet</div>
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={liveBuckets} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #1f2937', borderRadius: '8px', fontSize: '12px' }}
                labelStyle={{ color: '#9ca3af' }}
              />
              <Bar dataKey="count" fill="#34d399" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
