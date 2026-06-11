import { useEffect, useState, useRef, useCallback } from 'react'

export function useVisibleSections(): Set<string> {
  const [visible, setVisible] = useState<Set<string>>(new Set())
  const containerRef = useRef<HTMLDivElement | null>(null)

  const updateVisible = useCallback(() => {
    const ids = new Set<string>()
    const els = containerRef.current?.querySelectorAll('[data-monitor]')
    if (!els) return
    const threshold = 0.1
    for (const el of els) {
      const rect = el.getBoundingClientRect()
      const vh = window.innerHeight
      const visibleRatio = Math.max(0, Math.min(rect.bottom, vh) - Math.max(rect.top, 0)) / rect.height
      if (visibleRatio >= threshold) {
        ids.add(el.id || el.getAttribute('data-section-id') || '')
      }
    }
    setVisible(ids)
  }, [])

  useEffect(() => {
    // Set ref after mount
    containerRef.current = document.querySelector('[data-viewport]') as HTMLDivElement
    updateVisible()

    const observer = new IntersectionObserver(
      () => updateVisible(),
      { threshold: [0, 0.1, 0.2, 0.5, 1] },
    )

    const els = containerRef.current?.querySelectorAll('[data-monitor]')
    if (els) {
      els.forEach(el => observer.observe(el))
    }

    window.addEventListener('scroll', updateVisible, { passive: true })
    return () => {
      observer.disconnect()
      window.removeEventListener('scroll', updateVisible)
    }
  }, [updateVisible])

  return visible
}
