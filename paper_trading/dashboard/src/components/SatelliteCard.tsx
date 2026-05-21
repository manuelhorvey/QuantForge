import { usePortfolioState } from '../hooks/usePortfolioState'

export default function SatelliteCard() {
  const { data } = usePortfolioState()
  const sat = data?.engine_status?.satellite

  if (!sat) {
    return (
      <div className="card-gradient card-border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
          <span className="text-[11px] text-tertiary font-medium tracking-wide">BTC SATELLITE</span>
        </div>
        <div className="text-xs text-tertiary">Not initialized</div>
      </div>
    )
  }

  const ddColor = sat.drawdown_pct > -5 ? 'text-emerald-400' : sat.drawdown_pct > -15 ? 'text-amber-400' : 'text-red-400'
  const retColor = sat.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
  const gateColor = sat.gate_open ? 'text-emerald-400' : 'text-amber-400'
  const posColor = sat.position_active ? 'text-emerald-400' : 'text-gray-500'

  return (
    <div className="card-gradient card-border rounded-xl p-4 hover-lift">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
        <span className="text-[11px] text-tertiary font-medium tracking-wide">BTC SATELLITE</span>
        <span className={`ml-auto text-[10px] font-mono font-semibold ${gateColor}`}>
          {sat.gate_open ? 'GATE OPEN' : 'GATE CLOSED'}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs mb-3">
        <div className="bg-panel rounded-lg p-2">
          <div className="text-[10px] text-tertiary mb-0.5">Value</div>
          <div className={`font-mono text-[13px] font-bold ${retColor}`}>
            ${sat.current_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
        <div className="bg-panel rounded-lg p-2">
          <div className="text-[10px] text-tertiary mb-0.5">Return</div>
          <div className={`font-mono text-[13px] font-bold ${retColor}`}>
            {sat.total_return_pct >= 0 ? '+' : ''}{sat.total_return_pct.toFixed(2)}%
          </div>
        </div>
        <div className="bg-panel rounded-lg p-2">
          <div className="text-[10px] text-tertiary mb-0.5">Drawdown</div>
          <div className={`font-mono text-[13px] font-bold ${ddColor}`}>
            {sat.drawdown_pct.toFixed(2)}%
          </div>
        </div>
        <div className="bg-panel rounded-lg p-2">
          <div className="text-[10px] text-tertiary mb-0.5">Allocation</div>
          <div className="font-mono text-[13px] font-bold text-primary">
            {(sat.allocation_pct * 100).toFixed(1)}%
          </div>
        </div>
      </div>

      {sat.sharpe_contribution != null && (
        <div className="bg-panel/30 border border-default/40 rounded-lg px-2.5 py-1.5 flex items-center justify-between text-[11px] text-tertiary mb-2">
          <span>ΔSharpe (63d)</span>
          <span className={`font-mono font-semibold ${sat.sharpe_contribution >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {sat.sharpe_contribution >= 0 ? '+' : ''}{sat.sharpe_contribution.toFixed(2)}
          </span>
        </div>
      )}

      <div className="flex items-center gap-2 text-[11px] text-tertiary mb-1.5">
        <span className={`w-2 h-2 rounded-full ${posColor}`} />
        <span className={posColor}>{sat.position_active ? 'POSITION ACTIVE' : 'NO POSITION'}</span>
      </div>

      {!sat.gate_open && sat.gate_reasons.length > 0 && (
        <div className="mt-2 pt-2 border-t border-default/50">
          <div className="text-[10px] text-tertiary mb-1 font-medium">GATE BLOCKED BY:</div>
          {sat.gate_reasons.map((r, i) => (
            <div key={i} className="text-[10px] text-amber-400/70 font-mono pl-2">· {r}</div>
          ))}
        </div>
      )}
    </div>
  )
}
