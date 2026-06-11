export const TOKENS = {
  colors: {
    state: {
      GREEN: 'var(--color-state-green)',
      YELLOW: 'var(--color-state-yellow)',
      RED: 'var(--color-state-red)',
      NEUTRAL: 'var(--color-state-neutral)',
    },
    domain: {
      prediction: '#3b82f6',
      execution: '#a855f7',
      exit: '#22c55e',
      friction: '#f97316',
    },
  },
  spacing: {
    xs: '0.5rem',
    sm: '1rem',
    md: '1.5rem',
    lg: '2rem',
    xl: '3rem',
  },
  typography: {
    display: { size: '2.5rem', weight: 700, lineHeight: 1.2 },
    heading: { size: '2rem', weight: 700, lineHeight: 1.3 },
    title: { size: '1.5rem', weight: 600, lineHeight: 1.4 },
    body: { size: '1rem', weight: 400, lineHeight: 1.5 },
    caption: { size: '0.875rem', weight: 500, lineHeight: 1.4 },
  },
} as const

export function stateColor(score: number): string {
  if (score >= 0.8) return TOKENS.colors.state.GREEN
  if (score >= 0.5) return TOKENS.colors.state.YELLOW
  return TOKENS.colors.state.RED
}

export function domainColor(key: keyof typeof TOKENS.colors.domain): string {
  return TOKENS.colors.domain[key]
}
