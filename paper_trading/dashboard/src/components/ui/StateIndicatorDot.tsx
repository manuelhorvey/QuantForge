import type { GovernanceState } from './governance'
import { governanceDot } from './governance'

interface StateIndicatorDotProps {
  state: GovernanceState
  animate?: boolean
  className?: string
  size?: 'sm' | 'md'
}

const sizeMap = {
  sm: 'w-2 h-2',
  md: 'w-2.5 h-2.5',
}

const motionMap: Record<GovernanceState, string> = {
  GREEN: '',
  YELLOW: 'animate-pulse-subtle',
  RED: 'animate-pulse',
  INIT: '',
}

export default function StateIndicatorDot({
  state,
  animate = true,
  className = '',
  size = 'sm',
}: StateIndicatorDotProps) {
  return (
    <span
      className={`inline-block rounded-full shrink-0 ${sizeMap[size]} ${governanceDot[state]} ${animate ? motionMap[state] : ''} ${className}`}
      aria-hidden
    />
  )
}
