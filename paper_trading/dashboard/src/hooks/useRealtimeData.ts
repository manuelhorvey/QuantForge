import { useRef, useEffect, useState, useCallback } from 'react'

interface RealtimeConfig {
  url?: string
  fallbackPollMs?: number
  onMessage?: (data: Record<string, unknown>) => void
}

const WS_HOST = window.location.hostname || 'localhost'

function applyDelta<T extends Record<string, unknown>>(prev: T, delta: Partial<T>): T {
  const next = { ...prev }
  for (const [key, value] of Object.entries(delta)) {
    if (value !== undefined && value !== null) {
      ;(next as Record<string, unknown>)[key] = value
    }
  }
  return next
}

export function useRealtimeData<T extends Record<string, unknown>>(
  config: RealtimeConfig = {},
  initialState: T,
): {
  data: T
  isConnected: boolean
  lastUpdate: Date | null
} {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const [data, setData] = useState<T>(initialState)
  const [isConnected, setIsConnected] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  const wsUrl = config.url ?? `ws://${WS_HOST}:8000/ws`
  const fallbackMs = config.fallbackPollMs ?? 30_000

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => setIsConnected(true)

      ws.onmessage = (event) => {
        try {
          const update = JSON.parse(event.data)
          setData(prev => applyDelta(prev, update.data ?? update))
          setLastUpdate(new Date())
          config.onMessage?.(update)
        } catch {
          // silently ignore invalid messages
        }
      }

      ws.onclose = () => {
        setIsConnected(false)
        wsRef.current = null
        // Reconnect after delay
        reconnectTimer.current = setTimeout(connect, 5000)
      }

      ws.onerror = () => {
        ws?.close()
      }
    } catch {
      // WebSocket not available, rely on polling
      setIsConnected(false)
    }
  }, [wsUrl, config])

  useEffect(() => {
    connect()
    return () => {
      wsRef.current?.close()
      clearTimeout(reconnectTimer.current)
    }
  }, [connect])

  return { data, isConnected, lastUpdate }
}

export { applyDelta }
