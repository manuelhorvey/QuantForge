import type { ReactNode } from 'react'

type PanelVariant = 'default' | 'elevated' | 'flat' | 'accent'

interface PanelProps {
  children: ReactNode
  className?: string
  padding?: 'md' | 'lg' | 'none'
  variant?: PanelVariant
  hoverable?: boolean
  onClick?: () => void
  leftAccent?: string
}

const paddingMap = {
  md: 'p-3.5 sm:p-4',
  lg: 'p-4 sm:p-5',
  none: '',
}

const variantStyles: Record<PanelVariant, string> = {
  default: 'bg-panel border border-default shadow-panel',
  elevated: 'bg-panel border border-default shadow-card',
  flat: 'bg-panel border border-default',
  accent: 'bg-panel border border-default shadow-panel border-t-accent-emerald/50',
}

export default function Panel({
  children,
  className = '',
  padding = 'md',
  variant = 'default',
  hoverable = false,
  onClick,
  leftAccent,
}: PanelProps) {
  const hoverStyles = hoverable
    ? 'cursor-pointer hover:border-strong hover:shadow-card transition-all duration-200'
    : ''

  return (
    <div
      onClick={onClick}
      className={[
        'rounded-lg relative',
        variantStyles[variant],
        paddingMap[padding],
        hoverStyles,
        leftAccent ? 'border-l-2' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      style={leftAccent ? { borderLeftColor: leftAccent } : undefined}
    >
      {children}
    </div>
  )
}
