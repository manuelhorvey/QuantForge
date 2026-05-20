import { useMemo, useState, useEffect } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import type { EquityHistoryPoint } from '../types/portfolio'

async function fetchEquity(): Promise<EquityHistoryPoint[]> {
  const res = await fetch('/equity_history.json')
  if (!res.ok) return []
  return res.json()
}

const COLORS = ['#34d399', '#f87171', '#fbbf24', '#60a5fa', '#a78bfa', '#f472b6', '#2dd4bf', '#fb923c', '#94a3b8', '#e879f9', '#22d3ee']

export default function EquityChart() {
  const [data, setData] = useState<EquityHistoryPoint[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set(['portfolio']))

  useEffect(() => {
    fetchEquity().then(d => {
      setData(d)
      if (d.length > 0) {
        setSelected(prev => {
          const next = new Set(prev)
          next.add('portfolio')
          Object.keys(d[0].assets ?? {}).forEach(a => next.add(a))
          return next
        })
      }
    })
    const id = setInterval(() => {
      fetchEquity().then(d => {
        setData(d)
        if (d.length > 0) {
          setSelected(prev => {
            const next = new Set(prev)
            Object.keys(d[0].assets ?? {}).forEach(a => next.add(a))
            return next
          })
        }
      })
    }, 60_000)
    return () => clearInterval(id)
  }, [])

  const chartData = useMemo(() => data.map(d => ({
    t: d.timestamp?.split('T')[0] ?? '',
    portfolio: d.portfolio_value,
    ...d.assets,
  })), [data])

  const assetNames = useMemo(() => {
    if (data.length === 0) return []
    return Object.keys(data[0].assets ?? {}).sort()
  }, [data])

  const toggle = (name: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  if (chartData.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
        <h2 className="text-sm font-semibold mb-3">Equity Curve</h2>
        <div className="text-xs text-gray-400 dark:text-gray-500 text-center py-8">Waiting for data...</div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold">Equity Curve</h2>
        <span className="text-xs text-gray-400 dark:text-gray-500">{chartData.length} points</span>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {['portfolio', ...assetNames].map(name => {
          const active = selected.has(name)
          const color = name === 'portfolio' ? '#34d399' : COLORS[assetNames.indexOf(name) % COLORS.length]
          return (
            <button
              key={name}
              onClick={() => toggle(name)}
              className={`px-1.5 py-0.5 rounded border text-[10px] font-medium transition-colors ${
                active ? 'text-gray-50 dark:text-gray-900 border-gray-400 dark:border-gray-600' : 'text-gray-500 border-gray-700 hover:border-gray-500'
              }`}
              style={active ? { backgroundColor: color + '30', borderColor: color } : {}}
            >
              {name}
            </button>
          )
        })}
      </div>

      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="t" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} domain={['auto', 'auto']} />
            <Tooltip
              contentStyle={{ background: '#111827', border: '1px solid #1f2937', borderRadius: '8px', fontSize: '12px' }}
              labelStyle={{ color: '#9ca3af' }}
            />
            {selected.has('portfolio') && (
              <Area type="monotone" dataKey="portfolio" stroke="#34d399" fill="#34d399" fillOpacity={0.1} strokeWidth={2} name="Portfolio" />
            )}
            {assetNames.map((a, i) =>
              selected.has(a) ? (
                <Area key={a} type="monotone" dataKey={a} stroke={COLORS[i % COLORS.length]} fill={COLORS[i % COLORS.length]} fillOpacity={0.05} strokeWidth={1.5} name={a} />
              ) : null
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
