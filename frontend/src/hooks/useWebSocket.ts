import { useEffect, useRef } from 'react'
import { getToken } from '../api/client'
import type { ForwardEvent } from '../api/client'

export function useWebSocket(onEvent: (event: ForwardEvent) => void) {
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    let ws: WebSocket
    let reconnectTimer: ReturnType<typeof setTimeout>
    let destroyed = false

    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const token = getToken()
      if (!token) return
      ws = new WebSocket(`${protocol}//${window.location.host}/ws/events?token=${encodeURIComponent(token)}`)

      ws.onmessage = (e: MessageEvent) => {
        try {
          const event = JSON.parse(e.data as string) as ForwardEvent
          onEventRef.current(event)
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        if (!destroyed) {
          reconnectTimer = setTimeout(connect, 3000)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      destroyed = true
      clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [])
}
