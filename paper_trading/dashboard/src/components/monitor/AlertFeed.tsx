import { useState } from 'react'
import { X, AlertTriangle, AlertCircle, Info, Shield, Activity } from 'lucide-react'
import type { Alert } from '../../hooks/useMonitorAlerts'
import { dismissAlert } from '../../hooks/useMonitorAlerts'
import Panel from '../ui/Panel'
import SectionHeader from '../ui/SectionHeader'

interface AlertFeedProps {
  alerts: Alert[]
}

const severityConfig = {
  critical: { icon: AlertCircle, color: 'text-gov-red', bg: 'bg-gov-red-muted', border: 'border-gov-red/25' },
  warning: { icon: AlertTriangle, color: 'text-gov-yellow', bg: 'bg-gov-yellow-muted', border: 'border-gov-yellow/25' },
  info: { icon: Info, color: 'text-gov-init', bg: 'bg-gov-init-muted', border: 'border-gov-init/25' },
}

const typeIcon = {
  health: Shield,
  halt: AlertCircle,
  governance: Shield,
  performance: Activity,
}

export default function AlertFeed({ alerts }: AlertFeedProps) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  const visible = alerts.filter(a => !dismissed.has(a.id))

  const handleDismiss = (id: string) => {
    setDismissed(prev => new Set([...prev, id]))
    dismissAlert(id)
  }

  if (visible.length === 0) return null

  return (
    <Panel padding="md">
      <SectionHeader
        title="Active Alerts"
        accent="amber"
        meta={
          <span className="text-[10px] text-tertiary font-mono bg-surface px-2 py-0.5 rounded border border-default">
            {visible.length} active
          </span>
        }
      />
      <div className="space-y-1.5">
        {visible.map(alert => {
          const sev = severityConfig[alert.severity]
          const Icon = sev.icon
          const TypeIcon = typeIcon[alert.type]
          return (
            <div
              key={alert.id}
              className={`flex items-start gap-2 px-2.5 py-2 rounded-md border ${sev.bg} ${sev.border} transition-opacity`}
            >
              <TypeIcon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${sev.color}`} strokeWidth={2} />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-primary">{alert.message}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className={`text-[10px] font-semibold uppercase ${sev.color}`}>{alert.severity}</span>
                  <span className="text-[10px] text-tertiary font-mono">{alert.asset}</span>
                </div>
              </div>
              <button
                onClick={() => handleDismiss(alert.id)}
                className="p-0.5 rounded hover:bg-default/40 transition-colors shrink-0 mt-0.5"
                title="Dismiss"
              >
                <X className="w-3 h-3 text-tertiary" strokeWidth={2} />
              </button>
            </div>
          )
        })}
      </div>
    </Panel>
  )
}
