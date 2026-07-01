import { memo, useState, useEffect } from 'react'
import { Menu, RefreshCw } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

interface HeaderProps {
  onMenuClick?: () => void
}

/**
 * Header — the page-controls band beneath the TickerRail sign.
 *
 * After Phase D-9 (collapse MT5 / engine / seq into TickerRail),
 * the Header's only remaining jobs are:
 *   - mobile-only nav menu toggle (off-canvas sidebar)
 *   - dashboard data refresh (invalidate the React Query cache)
 *
 * The brand wordmark, seq# id, engine state, and MT5 status all
 * live in the rail. The HealthButton that opened SystemHealthModal
 * moved to the rail in Phase D-4 (it was an icon-only click target
 * duplicate). So nothing stays in Header except operator controls.
 */
function Header({ onMenuClick }: HeaderProps) {
  const queryClient = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    await queryClient.invalidateQueries()
    setTimeout(() => setRefreshing(false), 800)
  }

  return (
    <header
      className={`sticky top-[32px] z-30 bg-app/90 backdrop-blur-md border-b transition-shadow duration-200 ${
        scrolled ? 'border-default shadow-[0_1px_0_rgba(255,255,255,0.04)]' : 'border-default/60'
      }`}
    >
      <div className="max-w-[90rem] mx-auto px-2 sm:px-6 py-1 flex items-center justify-between gap-1 sm:gap-2">
        <button
          type="button"
          onClick={onMenuClick}
          className="lg:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md border border-default hover:border-strong hover:bg-panel transition-colors active:scale-95 focus-ring"
          title="Menu"
          aria-label="Open navigation menu"
        >
          <Menu className="w-3 h-3 text-secondary" strokeWidth={2} />
        </button>

        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-md border border-default hover:border-strong hover:bg-panel transition-colors disabled:opacity-40 active:scale-95 focus-ring"
          title="Refresh"
          aria-label="Refresh dashboard data"
        >
          <RefreshCw className={`w-3 h-3 text-secondary ${refreshing ? 'animate-spin' : ''}`} strokeWidth={2} />
        </button>
      </div>
    </header>
  )
}

export default memo(Header)
