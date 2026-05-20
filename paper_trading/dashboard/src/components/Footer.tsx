import { usePortfolioState } from '../hooks/usePortfolioState'
import { useSessionClock } from '../hooks/useSessionClock'

export default function Footer() {
  const { data } = usePortfolioState()
  const { timeStr, marketsOpen } = useSessionClock()
  const p = data?.portfolio
  const startDate = p?.start_date
  const gateDate = startDate ? new Date(new Date(startDate).getTime() + 180 * 86400000) : null

  const sessionInfo = (() => {
    if (!data?.assets) return ''
    const names = Object.keys(data.assets).sort()
    return marketsOpen ? names.join(', ') : 'All markets closed'
  })()

  return (
    <footer className="border-t border-gray-200 dark:border-gray-800 px-6 py-3 text-xs text-gray-400 dark:text-gray-500">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2">
        <span>
          Next retrain: <strong className="text-gray-300">Jan 1, {new Date().getFullYear() + 1}</strong>
        </span>
        <span>
          Started: <strong className="text-gray-300">{startDate ? new Date(startDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</strong>
        </span>
        <span>
          6-month gate: <strong className="text-gray-300">{gateDate ? gateDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</strong>
        </span>
        <span>
          Cleared: <strong className={p?.deployment_cleared ? 'text-emerald-400' : 'text-amber-400'}>{p?.deployment_cleared ? 'Yes' : 'No'}</strong>
        </span>
        <span className="hidden md:inline truncate max-w-xs">
          Sessions: {sessionInfo}
        </span>
      </div>
    </footer>
  )
}
