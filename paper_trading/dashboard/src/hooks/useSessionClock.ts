import { useState, useEffect } from 'react'
import { format } from 'date-fns'

const ET = 'America/New_York'

function toZonedTime(date: Date, tz: string): Date {
  const s = date.toLocaleString('en-US', { timeZone: tz })
  return new Date(s)
}

interface SessionInfo {
  timeStr: string
  dateStr: string
  day: number
  hour: number
  minute: number
  marketsOpen: boolean
}

export function isMarketOpen(day: number, hour: number): boolean {
  if (day === 6) return false
  if (day === 0) return hour >= 17 || hour < 0
  return true
}

export function useSessionClock(): SessionInfo {
  const [clock, setClock] = useState<SessionInfo>(() => {
    const now = new Date()
    const zoned = toZonedTime(now, ET)
    return {
      timeStr: format(zoned, 'HH:mm:ss'),
      dateStr: format(zoned, 'MMM dd, yyyy'),
      day: zoned.getDay(),
      hour: zoned.getHours(),
      minute: zoned.getMinutes(),
      marketsOpen: isMarketOpen(zoned.getDay(), zoned.getHours()),
    }
  })

  useEffect(() => {
    const id = setInterval(() => {
      const now = new Date()
      const zoned = toZonedTime(now, ET)
      setClock({
        timeStr: format(zoned, 'HH:mm:ss'),
        dateStr: format(zoned, 'MMM dd, yyyy'),
        day: zoned.getDay(),
        hour: zoned.getHours(),
        minute: zoned.getMinutes(),
        marketsOpen: isMarketOpen(zoned.getDay(), zoned.getHours()),
      })
    }, 1000)
    return () => clearInterval(id)
  }, [])

  return clock
}
