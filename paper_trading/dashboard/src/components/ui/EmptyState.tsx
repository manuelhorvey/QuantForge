import { Inbox, SearchSlash } from 'lucide-react'

interface EmptyStateProps {
  message: string
  hint?: string
  compact?: boolean
  filtered?: boolean
  section?: 'portfolio' | 'trades' | 'execution' | 'risk' | 'monitor'
}

const sectionHints: Record<string, string> = {
  portfolio: 'Engine will populate as assets are initialised and data flows in.',
  trades: 'Closed trades appear here once the first TP/SL/Flip event occurs.',
  execution: 'Execution metrics populate after the first round-trip trade completes.',
  risk: 'Risk data becomes available after sufficient trading history accumulates.',
  monitor: 'Health snapshots update as the paper trading engine processes bars.',
}

export default function EmptyState({ message, hint, compact, filtered, section }: EmptyStateProps) {
  const Icon = filtered ? SearchSlash : Inbox
  const contextualHint = hint ?? (section ? sectionHints[section] : undefined)
  return (
    <div
      className={`flex flex-col items-center justify-center text-center ${
        compact ? 'py-10 px-4' : 'py-16 px-6'
      }`}
    >
      <Icon
        className={`text-tertiary/40 mb-2 ${compact ? 'w-5 h-5' : 'w-7 h-7'}`}
        strokeWidth={1.25}
      />
      <p className={`text-tertiary ${compact ? 'text-xs' : 'text-sm'}`}>{message}</p>
      {contextualHint != null && <p className="text-muted text-[10px] mt-2 max-w-xs leading-relaxed">{contextualHint}</p>}
    </div>
  )
}
