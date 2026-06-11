import { useEffect, useState } from 'react'

export const SECTION_IDS = ['monitor', 'portfolio', 'signals', 'execution', 'trades', 'risk'] as const
export type SectionId = typeof SECTION_IDS[number]

export function useActiveSection() {
  const [active, setActive] = useState<string>('portfolio')

  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActive(entry.target.id)
          }
        }
      },
      { rootMargin: '-80px 0px -60% 0px', threshold: 0 },
    )

    const els: Element[] = []
    for (const id of SECTION_IDS) {
      const el = document.getElementById(id)
      if (el) {
        observer.observe(el)
        els.push(el)
      }
    }

    return () => {
      for (const el of els) observer.unobserve(el)
      observer.disconnect()
    }
  }, [])

  return active
}
