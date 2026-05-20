import { useEffect, useState } from 'react'
import { usePortfolioState } from '../hooks/usePortfolioState'
import { useSessionClock } from '../hooks/useSessionClock'

export default function Header() {
  const { dataUpdatedAt, isError, data } = usePortfolioState()
  const { timeStr, dateStr, marketsOpen } = useSessionClock()
  const [dark, setDark] = useState(() => localStorage.getItem('theme') !== 'light')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  const staleness = dataUpdatedAt ? Date.now() - dataUpdatedAt : Infinity
  const statusColor =
    isError || staleness > 120_000 ? 'text-red-400' : staleness > 35_000 ? 'text-amber-400' : 'text-emerald-400'
  const statusText =
    isError ? 'Disconnected' : staleness > 120_000 ? 'Stale' : staleness > 35_000 ? 'Delayed' : 'Live'
  const daysRunning = data?.portfolio?.days_running ?? 0

  return (
    <header className="border-b border-gray-200 dark:border-gray-800 px-6 py-4">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-bold tracking-tight">QuantForge</h1>
          <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">v2</span>
        </div>

        <div className="flex items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <span className={`inline-block w-2 h-2 rounded-full ${statusColor} ${isError ? '' : 'animate-pulse'}`} />
            <span className={`font-mono ${statusColor}`}>{statusText}</span>
          </div>

          <div className="flex items-center gap-2 text-gray-400 dark:text-gray-500">
            <span>{dateStr}</span>
            <span className="font-mono">{timeStr}</span>
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
              marketsOpen ? 'bg-emerald-950 text-emerald-400' : 'bg-red-950 text-red-400'
            }`}>
              {marketsOpen ? 'OPEN' : 'CLOSED'}
            </span>
          </div>

          <span className="text-gray-400 dark:text-gray-500">
            {daysRunning > 0 ? `${daysRunning}d` : '—'}
          </span>

          <button
            onClick={() => setDark(d => !d)}
            className="p-1.5 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-500 transition-colors"
            title="Toggle theme"
          >
            {dark ? (
              <svg className="w-4 h-4 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            ) : (
              <svg className="w-4 h-4 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </header>
  )
}
