import { useMemo, useEffect, useState } from 'react'
import { usePortfolioState } from '../hooks/usePortfolioState'
import type { VolRegime } from '../types/portfolio'

const VOL_BASELINES: Record<string, number> = {
  BTC: 0.038705,
  GC: 0.009129,
  NZDJPY: 0.006581,
  CADJPY: 0.005989,
  USDCAD: 0.004463,
  EURAUD: 0.005026,
  AUDJPY: 0.006759,
  GBPJPY: 0.006138,
  USDJPY: 0.004498,
  USDCHF: 0.004307,
  GBPUSD: 0.005595,
}

function volStatus(ratio: number): VolRegime['status'] {
  if (ratio >= 0.8 && ratio <= 1.2) return 'green'
  if ((ratio >= 0.7 && ratio < 0.8) || (ratio > 1.2 && ratio <= 1.3)) return 'amber'
  return 'red'
}

export default function VolRegimePanel() {
  const { data } = usePortfolioState()

  const regimes = useMemo((): VolRegime[] => {
    if (!data?.assets) return []
    return Object.entries(data.assets)
      .map(([name, asset]) => {
        const trainingVol = VOL_BASELINES[name]
        const currentVol = asset.metrics?.position?.current_vol
        if (trainingVol == null || currentVol == null) return null
        const ratio = trainingVol > 0 ? currentVol / trainingVol : 1
        return { asset: name, training_vol: trainingVol, current_vol: currentVol, ratio, status: volStatus(ratio) }
      })
      .filter((r): r is VolRegime => r !== null)
      .sort((a, b) => a.asset.localeCompare(b.asset))
  }, [data])

  return (
    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
      <h2 className="text-sm font-semibold mb-3">Vol Regime</h2>
      {regimes.length === 0 ? (
        <div className="text-xs text-gray-400 dark:text-gray-500 text-center py-8">No position data yet</div>
      ) : (
        <div className="space-y-2">
          {regimes.map(r => (
            <div key={r.asset} className="flex items-center justify-between text-xs py-1.5 border-b border-gray-200 dark:border-gray-800 last:border-0">
              <span className="font-medium w-16">{r.asset}</span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                r.status === 'green' ? 'bg-emerald-950 text-emerald-400' :
                r.status === 'amber' ? 'bg-amber-950 text-amber-400' :
                'bg-red-950 text-red-400'
              }`}>
                {r.status.toUpperCase()}
              </span>
              <span className="font-mono text-gray-400 dark:text-gray-500">
                {r.current_vol.toFixed(4)}
              </span>
              <span className="font-mono text-gray-500">
                / {r.training_vol.toFixed(4)}
              </span>
              <span className={`font-mono w-12 text-right ${
                r.status === 'green' ? 'text-emerald-400' : r.status === 'amber' ? 'text-amber-400' : 'text-red-400'
              }`}>
                {r.ratio.toFixed(2)}x
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
