import { useMemo } from 'react'
import { usePortfolioState } from './usePortfolioState'
import { useHealthScores } from './useHealthScores'

export interface Alert {
  id: string
  type: 'health' | 'halt' | 'governance' | 'performance'
  asset: string
  severity: 'critical' | 'warning' | 'info'
  message: string
  timestamp: string
}

const DISMISSED_KEY = 'qf-dismissed-alerts'

function loadDismissed(): Set<string> {
  try {
    const raw = sessionStorage.getItem(DISMISSED_KEY)
    return new Set(raw ? JSON.parse(raw) : [])
  } catch {
    return new Set()
  }
}

export function dismissAlert(id: string) {
  const dismissed = loadDismissed()
  dismissed.add(id)
  try {
    sessionStorage.setItem(DISMISSED_KEY, JSON.stringify([...dismissed]))
  } catch {}
}

export function useMonitorAlerts(): Alert[] {
  const { data: state } = usePortfolioState()
  const { data: health } = useHealthScores()

  return useMemo(() => {
    const alerts: Alert[] = []
    const dismissed = loadDismissed()
    const now = state?.timestamp ?? new Date().toISOString()

    // Health alerts
    if (health?.assets) {
      for (const [name, h] of Object.entries(health.assets)) {
        if (h.health_score < 0.5) {
          alerts.push({
            id: `health-critical-${name}`,
            type: 'health',
            asset: name,
            severity: 'critical',
            message: `${name} health is critical (${(h.health_score * 100).toFixed(0)}%)`,
            timestamp: now,
          })
        } else if (h.health_score < 0.8) {
          alerts.push({
            id: `health-degraded-${name}`,
            type: 'health',
            asset: name,
            severity: 'warning',
            message: `${name} health degraded (${(h.health_score * 100).toFixed(0)}%)`,
            timestamp: now,
          })
        }
      }
    }

    // Halt alerts
    if (state?.halt_conditions) {
      for (const [name, asset] of Object.entries(state.assets ?? {})) {
        if (asset.halt?.halted) {
          alerts.push({
            id: `halt-${name}`,
            type: 'halt',
            asset: name,
            severity: 'critical',
            message: `${name} halted — ${(asset.halt.reasons ?? []).join(', ') || 'unknown'}`,
            timestamp: now,
          })
        }
      }
    }

    // Governance alerts from halt thresholds
    if (state?.halt_conditions) {
      const hc = state.halt_conditions
      if (hc.drawdown > 0.15) {
        alerts.push({
          id: 'gov-drawdown',
          type: 'governance',
          asset: 'SYSTEM',
          severity: 'critical',
          message: `Portfolio drawdown threshold exceeded (${(hc.drawdown * 100).toFixed(1)}%)`,
          timestamp: now,
        })
      }
      if (hc.prob_drift > 0.3) {
        alerts.push({
          id: 'gov-psi',
          type: 'governance',
          asset: 'SYSTEM',
          severity: 'warning',
          message: `PSI drift elevated (${(hc.prob_drift * 100).toFixed(0)}%)`,
          timestamp: now,
        })
      }
    }

    return alerts.filter(a => !dismissed.has(a.id)).slice(0, 20)
  }, [health, state])
}
