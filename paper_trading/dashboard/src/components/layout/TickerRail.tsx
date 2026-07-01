import { useMemo } from 'react'
import { useSystemSnapshot } from '../../hooks/useSystemSnapshot'
import { useEngineHealth } from '../../hooks/useEngineHealth'
import { systemSelectors } from '../../selectors/system'

/**
 * TickerRail — operator-console signature element.
 *
 * A 32px-tall mono breadcrumb pinned above <Header>. Reads as a single
 * continuous string of facts the operator needs at every glance:
 *   seq · engine · last tick · pek · halt · assets · mt5
 *
 * One fact per word. A field turning negative replaces its word with
 * a coloured token rather than restructuring the rail. When the
 * engine halts the entire rail renders an inline halt-because-word.
 *
 * The Header's old "brand line" + HealthBadge + MT5Status + seq#
 * combination all carry a fact already encoded in the rail; the
 * Header became a single slim row of page-controls (menu / refresh)
 * once these facts were collapsed here.
 */
type TokenTone = 'good' | 'warn' | 'bad' | 'muted'

interface RailToken {
  label: string
  value: string
  tone?: TokenTone
}

function toneClass(tone?: TokenTone): string {
  switch (tone) {
    case 'good': return 'text-gov-green'
    case 'warn': return 'text-gov-yellow'
    case 'bad':  return 'text-gov-red'
    default:     return 'text-tertiary'
  }
}

function classifyMt5(state: string, equity: number | null): { value: string; tone: TokenTone } {
  if (state === 'ERROR') return { value: 'ERROR', tone: 'bad' }
  if (state === 'CONNECTED') {
    return { value: equity != null ? `live $${equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : 'live', tone: 'good' }
  }
  if (state === 'DISCONNECTED') return { value: 'disc', tone: 'warn' }
  return { value: 'unknown', tone: 'muted' }
}

export default function TickerRail() {
  const { data: snapshot }   = useSystemSnapshot(systemSelectors.snapshot)
  const { data: mt5Live }    = useSystemSnapshot(systemSelectors.mt5)
  const health = useEngineHealth()

  const parts = useMemo(() => {
    const now = Date.now()
    const lastUpdateMs = snapshot?.engine_status?.last_update
      ? Date.parse(snapshot.engine_status.last_update)
      : null
    const tickAgoSec = lastUpdateMs != null
      ? Math.max(0, Math.round((now - lastUpdateMs) / 1000))
      : null

    const engineState: 'alive' | 'stale' | 'dead' | null = health.isError
      ? 'dead'
      : (health.isLoading || health.data == null)
        ? null
        : health.data.engine_alive
          ? 'alive'
          : 'stale'

    const seqId      = snapshot?.sequence_id
    const admission  = snapshot?.portfolio?.admission
    const halted     = Boolean(snapshot?.emergency_halt)
    const haltReason = snapshot?.halt_reason ?? snapshot?.halt_detail
    const assetCount = snapshot?.assets ? Object.keys(snapshot.assets).length : null

    const mt5State = mt5Live?.status ?? 'UNKNOWN'
    const mt5Equity = mt5Live?.account?.portfolio_value != null
      ? Number(mt5Live.account.portfolio_value)
      : null

    const tokens: RailToken[] = []
    tokens.push({ label: 'Q', value: '·QUORRIN', tone: 'muted' })
    if (seqId != null) tokens.push({ label: 'seq', value: `#${seqId}` })
    if (engineState) {
      tokens.push({
        label: 'engine',
        value: engineState,
        tone: engineState === 'alive' ? 'good'
            : engineState === 'stale' ? 'warn'
            : 'bad',
      })
    }
    if (tickAgoSec != null) {
      tokens.push({
        label: 'tick',
        value: `${tickAgoSec}s`,
        tone: tickAgoSec <= 30 ? 'good' : tickAgoSec <= 120 ? 'warn' : 'bad',
      })
    }
    if (admission && admission.n_intents > 0) {
      tokens.push({
        label: 'pek',
        value: `${admission.n_admitted}/${admission.n_intents}`,
        tone: admission.n_rejected > 0 ? 'warn' : 'good',
      })
    }
    {
      const { value, tone } = classifyMt5(mt5State, mt5Equity)
      tokens.push({ label: 'mt5', value, tone })
    }
    if (halted) {
      tokens.push({ label: 'halt', value: 'YES', tone: 'bad' })
    } else {
      tokens.push({ label: 'halt', value: 'no', tone: 'muted' })
    }
    if (assetCount != null) tokens.push({ label: 'assets', value: String(assetCount) })

    return { tokens, haltReason, halted }
  }, [snapshot, health.isError, health.isLoading, health.data, mt5Live])

  if (parts.halted && parts.haltReason) {
    return (
      <div className="h-8 w-full px-2 sm:px-4 flex items-center gap-3 text-xs font-mono tabular-nums border-b border-default bg-gov-red/15 text-gov-red">
        <span className="font-bold">HALT</span>
        <span className="truncate">— {parts.haltReason}</span>
        <span className="ml-auto opacity-70">engine halted · all positions frozen</span>
      </div>
    )
  }

  return (
    <div className="h-8 w-full px-2 sm:px-4 flex items-center gap-3 text-xs font-mono tabular-nums border-b border-default bg-app/80 text-tertiary overflow-x-auto whitespace-nowrap">
      {parts.tokens.map((t, i) => (
        <span key={`${t.label}-${i}`} className="inline-flex items-center gap-1.5">
          <span className="uppercase tracking-wider text-muted/70">{t.label}</span>
          <span className={`font-semibold ${toneClass(t.tone)}`}>{t.value}</span>
          {i < parts.tokens.length - 1 && <span className="text-muted/40">·</span>}
        </span>
      ))}
    </div>
  )
}
