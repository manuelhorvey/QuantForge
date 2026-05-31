import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Sun, Moon, RefreshCw, Calendar, Clock, TrendingUp, Pause } from 'lucide-react'
import { usePortfolioState } from '../hooks/usePortfolioState'
import { useSessionClock } from '../hooks/useSessionClock'
import { useNarrative, useConfirmNarrative } from '../hooks/useNarrative'
import { useLiquidity } from '../hooks/useLiquidity'
import { format } from 'date-fns'
import ConnectionStatus from './ConnectionStatus'
import {
  governanceBadge,
  governanceDot,
  governanceText,
  type GovernanceState,
} from './ui/governance'

function ConfirmButton() {
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const confirmNarrative = useConfirmNarrative()
  return (
    <div className="relative">
      <button
        type="button"
        disabled={confirming}
        onClick={async () => {
          setConfirming(true)
          setError(null)
          try {
            await confirmNarrative()
          } catch (e) {
            const msg = e instanceof Error ? e.message : 'Confirm failed'
            console.error('[Narrative] confirm error:', msg)
            setError(msg)
            setTimeout(() => setError(null), 4000)
          }
          setConfirming(false)
        }}
        className={`flex items-center gap-1 px-2 py-1 rounded-md border text-2xs font-medium hover:bg-gov-yellow/20 transition-colors active:scale-95 disabled:opacity-50 ${governanceBadge.YELLOW}`}
        title="Confirm pending macro narrative"
      >
        <span className={`w-1.5 h-1.5 rounded-full ${confirming ? 'bg-muted' : governanceDot.YELLOW + ' animate-pulse'}`} />
        {confirming ? 'CONFIRMING...' : 'NARR PENDING'}
      </button>
      {error && (
        <div className={`absolute top-full mt-1 right-0 whitespace-nowrap px-2 py-1 rounded border text-2xs font-mono ${governanceBadge.RED}`}>
          {error}
        </div>
      )}
    </div>
  )
}

function connectionState(isDisconnected: boolean, marketsClosed: boolean, isDelayed: boolean): GovernanceState {
  if (isDisconnected) return 'RED'
  if (marketsClosed || isDelayed) return 'YELLOW'
  return 'GREEN'
}

export default function Header() {
  const { dataUpdatedAt, isError, isFetching, data } = usePortfolioState()
  const { data: narrative } = useNarrative()
  const { data: liquidity } = useLiquidity()
  const { timeStr, dateStr, marketsOpen } = useSessionClock()
  const [dark, setDark] = useState(() => localStorage.getItem('theme') !== 'light')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  const staleness = dataUpdatedAt ? Date.now() - dataUpdatedAt : Infinity
  const isLive = !isError && staleness <= 35_000
  const isDelayed = !isError && staleness > 35_000 && staleness <= 120_000
  const isDisconnected = isError

  const serverClosed = data?.engine_status?.market_closed === true
  const marketsClosed = serverClosed || !marketsOpen

  const connState: GovernanceState = connectionState(isDisconnected, marketsClosed, isDelayed)
  const statusText = isDisconnected ? 'Disconnected' : marketsClosed ? 'CLSD' : isDelayed ? 'Delayed' : 'Live'

  const daysRunning = data?.portfolio?.days_running ?? 0
  const queryClient = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)

  const lastUpdate = data?.engine_status?.last_update
  const lastRefreshStr = lastUpdate
    ? (() => { try { return format(new Date(lastUpdate), 'MMM dd, HH:mm') } catch { return '' } })()
    : ''

  const handleRefresh = async () => {
    setRefreshing(true)
    await queryClient.invalidateQueries()
    setTimeout(() => setRefreshing(false), 800)
  }

  return (
    <header className="sticky top-0 z-30 glass glass-border">
      <div className="max-w-[90rem] mx-auto px-3 sm:px-6 py-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-lg bg-gradient-to-br from-accent-emerald to-emerald-700 flex items-center justify-center shadow-glow-emerald shrink-0">
            <TrendingUp className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-surface" strokeWidth={2.25} />
          </div>
          <div className="min-w-0">
            <h1 className="text-sm font-bold tracking-tight text-primary leading-none truncate">QuantForge</h1>
            <p className="text-2xs text-muted uppercase tracking-widest mt-0.5 hidden sm:block">Paper Trading</p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded-md border transition-colors ${governanceBadge[connState]}`}>
            {marketsClosed && !isDisconnected ? (
              <Pause className="w-2.5 h-2.5" strokeWidth={2.5} />
            ) : (
              <span className={`relative inline-flex w-1.5 h-1.5 rounded-full bg-current ${isLive ? 'animate-pulse' : ''}`}>
                {isLive && <span className="absolute inset-0 rounded-full bg-current animate-ping opacity-30" />}
              </span>
            )}
            <span className="text-2xs font-semibold font-mono uppercase tracking-wide">{statusText}</span>
            {isFetching && <RefreshCw className="w-2 h-2 animate-spin opacity-70" strokeWidth={2.5} />}
          </div>

          <div className="hidden sm:flex">
            <ConnectionStatus />
          </div>

          <div className="hidden sm:flex items-center gap-1.5 text-2xs text-secondary border-l border-default pl-2">
            <span className="font-mono tabular-nums">{timeStr}</span>
            <span className="text-tertiary">·</span>
            <span className={marketsClosed ? governanceText.YELLOW + ' font-semibold' : governanceText.GREEN + ' font-semibold'}>
              {marketsClosed ? 'CLSD' : 'OPEN'}
            </span>
          </div>

          {lastRefreshStr && (
            <div className="hidden md:flex items-center gap-1 text-2xs text-tertiary font-mono tabular-nums border-l border-default pl-2">
              <span className="text-muted">LAST</span>
              <span className="text-secondary">{lastRefreshStr}</span>
            </div>
          )}

          <div className="hidden md:flex items-center gap-1 text-2xs text-tertiary font-mono tabular-nums">
            <span className="text-muted">RUN</span>
            <span className="text-secondary">{daysRunning > 0 ? `${daysRunning}d` : '—'}</span>
          </div>

          {narrative?.fetch_error && (
            <div
              className={`flex items-center gap-1 px-2 py-1 rounded-md border text-2xs font-medium ${governanceBadge.RED}`}
              title={`Narrative fetch error: ${JSON.stringify(narrative.fetch_error)}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${governanceDot.RED}`} />
              NARR ERR
            </div>
          )}

          {narrative?.needs_confirmation && <ConfirmButton />}

          {narrative?.active && !narrative.needs_confirmation && !narrative.fetch_error && (
            <div className="flex items-center gap-1 px-2 py-1 rounded-md border border-default/20 bg-panel text-2xs text-tertiary font-medium">
              <span className={`w-1.5 h-1.5 rounded-full ${
                narrative.active.overall_regime === 'risk_off' ? governanceDot.RED :
                narrative.active.overall_regime === 'geopol_tension' ? governanceDot.YELLOW :
                narrative.active.overall_regime === 'risk_on' ? governanceDot.GREEN :
                'bg-muted'
              }`} />
              {String(narrative.active.overall_regime).replace(/_/g, ' ').toUpperCase()}
              {narrative.stale && <span className={`${governanceText.YELLOW} ml-1 text-[10px]`}>(STALE)</span>}
            </div>
          )}

          {liquidity && Object.values(liquidity).some(l => l.regime !== 'NORMAL') && (
            <div
              className="flex items-center gap-1 px-2 py-1 rounded-md border border-default/20 bg-panel text-2xs text-tertiary font-medium"
              title={Object.entries(liquidity)
                .filter(([, l]) => l.regime !== 'NORMAL')
                .map(([a, l]) => `${a}: ${l.regime} sl=${l.sl_mult.toFixed(2)}x size=${l.size_scalar.toFixed(2)}x`)
                .join(' | ')}
            >
              {Object.values(liquidity).some(l => l.regime === 'STRESSED') ? (
                <span className={`w-1.5 h-1.5 rounded-full ${governanceDot.RED}`} />
              ) : (
                <span className={`w-1.5 h-1.5 rounded-full ${governanceDot.YELLOW}`} />
              )}
              LIQ {Object.values(liquidity).some(l => l.regime === 'STRESSED') ? 'STRSD' : 'THIN'}
            </div>
          )}

          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing}
            className="p-1.5 rounded-md border border-default hover:border-strong hover:bg-panel transition-colors disabled:opacity-40 active:scale-95"
            title="Refresh all data"
          >
            <RefreshCw className={`w-3 h-3 text-secondary ${refreshing ? 'animate-spin' : ''}`} strokeWidth={2} />
          </button>

          <button
            type="button"
            onClick={() => setDark(d => !d)}
            className="p-1.5 rounded-md border border-default hover:border-strong hover:bg-panel transition-colors active:scale-95"
            title="Toggle theme"
          >
            {dark ? (
              <Sun className={`w-3 h-3 ${governanceText.YELLOW}`} strokeWidth={2} />
            ) : (
              <Moon className="w-3 h-3 text-tertiary" strokeWidth={2} />
            )}
          </button>
        </div>
      </div>
    </header>
  )
}
