import { useEffect, useRef } from 'react'
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
      ws = new WebSocket(`${protocol}//${window.location.host}/ws/events`)

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
