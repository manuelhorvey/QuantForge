import { useTradingState } from '../lib/trading-state/hook'
import SystemHealthSummary from '../components/SystemHealthSummary'
import EdgeHealthAlert from '../components/EdgeHealthAlert'
import ExitPhaseIndicator from '../components/ExitPhaseIndicator'
import Panel from '../components/ui/Panel'
import Badge from '../components/ui/Badge'
import StatCard from '../components/ui/StatCard'
import EmptyState from '../components/ui/EmptyState'
import EntranceAnimator from '../components/ui/EntranceAnimator'

function TradingAssetRow({ asset }: { asset: ReturnType<typeof useTradingState>['assetList'][number] }) {
  const pnlColor = asset.pnl_state.unrealized >= 0 ? '#22c55e' : '#ef4444'

  return (
    <div className="flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-panel/60 transition-colors border border-transparent hover:border-default group">
      {/* Asset name + direction */}
      <div className="flex items-center gap-2 w-28 shrink-0">
        <span className="text-xs font-semibold text-primary font-mono">{asset.identity}</span>
        {asset.direction && (
          <Badge
            variant={asset.direction === 'LONG' ? 'success' : 'error'}
            size="sm"
            icon={asset.direction === 'LONG' ? 'long' : 'short'}
          >
            {asset.direction === 'LONG' ? 'L' : 'S'}
          </Badge>
        )}
      </div>

      {/* PnL */}
      <div className="w-20 shrink-0 text-right">
        <span className="text-xs font-mono tabular-nums font-semibold" style={{ color: pnlColor }}>
          {asset.pnl_state.unrealized >= 0 ? '+' : ''}{asset.pnl_state.unrealized.toFixed(2)}
        </span>
      </div>

      {/* Exit phase */}
      <div className="w-36 shrink-0">
        <ExitPhaseIndicator
          phase={asset.exit_state.phase}
          slIsDynamic={asset.exit_state.sl_is_dynamic}
          peakMfeR={asset.exit_state.peak_mfe_r}
        />
      </div>

      {/* Risk level */}
      <div className="w-20 shrink-0">
        <Badge
          variant={asset.risk_state.level === 'HIGH' ? 'error' : asset.risk_state.level === 'MEDIUM' ? 'warning' : 'success'}
          size="sm"
          dot
        >
          {asset.risk_state.level}
        </Badge>
      </div>

      {/* Flags */}
      <div className="flex-1 flex items-center gap-1 min-w-0">
        {asset.flags.slice(0, 2).map((flag) => (
          <Badge key={flag} variant="neutral" size="sm">
            {flag.replace(/_/g, ' ')}
          </Badge>
        ))}
      </div>
    </div>
  )
}

export default function TradingDashboard() {
  const { portfolio, assetList, isLoading } = useTradingState()

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* System health — single source of truth */}
      <SystemHealthSummary />

      {/* Key metrics row */}
      <EntranceAnimator variant="fade-up" delay={60}>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
          <StatCard
            label="Open Positions"
            value={assetList.filter(a => a.position_state === 'OPEN').length.toString()}
            sub={`${assetList.filter(a => a.direction === 'LONG').length}L / ${assetList.filter(a => a.direction === 'SHORT').length}S`}
            variant="compact"
          />
          <StatCard
            label="In Trailing"
            value={assetList.filter(a => a.exit_state.phase === 'TRAILING').length.toString()}
            sub={`+${assetList.filter(a => a.exit_state.phase === 'DECAY').length} decaying`}
            variant="compact"
          />
          <StatCard
            label="High Risk"
            value={assetList.filter(a => a.risk_state.level === 'HIGH').length.toString()}
            sub={assetList.filter(a => a.risk_state.level === 'MEDIUM').length + ' medium'}
            variant="compact"
          />
          <StatCard
            label="Flags Active"
            value={assetList.filter(a => a.flags.length > 0).length.toString()}
            sub="Assets needing attention"
            variant="compact"
          />
        </div>
      </EntranceAnimator>

      {/* Asset list — interpreted state only */}
      <EntranceAnimator variant="fade-up" delay={120}>
        <Panel padding="md">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-tertiary uppercase tracking-wider">Assets (Interpreted State)</span>
            <span className="text-[10px] text-tertiary">{assetList.length} assets</span>
          </div>
          {assetList.length === 0 && !isLoading ? (
            <EmptyState message="No asset data available" compact />
          ) : (
            <div className="divide-y divide-border/50">
              {/* Column headers */}
              <div className="flex items-center gap-3 px-2 pb-1.5 text-[10px] text-tertiary font-medium uppercase tracking-wider">
                <span className="w-28">Asset</span>
                <span className="w-20 text-right">PnL</span>
                <span className="w-36">Exit Phase</span>
                <span className="w-20">Risk</span>
                <span className="flex-1">Flags</span>
              </div>
              {assetList.map(asset => (
                <TradingAssetRow key={asset.identity} asset={asset} />
              ))}
            </div>
          )}
        </Panel>
      </EntranceAnimator>

      {/* Edge health */}
      <EntranceAnimator variant="fade-up" delay={180}>
        <EdgeHealthAlert />
      </EntranceAnimator>

      {/* Link to full dashboard */}
      <div className="text-center pb-4">
        <a
          href="#/engine"
          className="text-xs text-tertiary hover:text-secondary underline underline-offset-2 transition-colors"
        >
          Full engine dashboard →
        </a>
      </div>
    </div>
  )
}
