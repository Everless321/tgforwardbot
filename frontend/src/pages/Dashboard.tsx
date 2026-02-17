import { useState, useEffect, useCallback } from 'react'
import { fetchStatus, type Status, type ForwardEvent } from '../api/client'
import { useWebSocket } from '../hooks/useWebSocket'

const MAX_EVENTS = 20

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString()
}

export default function Dashboard() {
  const [status, setStatus] = useState<Status | null>(null)
  const [events, setEvents] = useState<ForwardEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  const loadStatus = useCallback(async () => {
    try {
      const data = await fetchStatus()
      setStatus(data)
      setError(null)
    } catch {
      setError('Failed to load status')
    }
  }, [])

  useEffect(() => {
    loadStatus()
    const timer = setInterval(loadStatus, 5000)
    return () => clearInterval(timer)
  }, [loadStatus])

  const handleEvent = useCallback((event: ForwardEvent) => {
    setEvents(prev => [event, ...prev].slice(0, MAX_EVENTS))
  }, [])

  useWebSocket(handleEvent)

  return (
    <div className="page">
      <h1 className="page-title">Dashboard</h1>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">Connection</div>
          <div className="stat-value">
            <span className={`dot ${status?.connected ? 'dot-green' : 'dot-red'}`} />
            {status?.connected ? 'Connected' : 'Disconnected'}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Active Rules</div>
          <div className="stat-value">{status?.rules_active ?? '—'} / {status?.rules_count ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Forwarded Today</div>
          <div className="stat-value success">{status?.messages_today ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Failed Today</div>
          <div className="stat-value danger">{status?.messages_failed_today ?? '—'}</div>
        </div>
      </div>

      {status?.last_forward_at && (
        <p className="meta-text">
          Last forward: {new Date(status.last_forward_at).toLocaleString()}
        </p>
      )}

      <h2 className="section-title">Recent Events</h2>
      {events.length === 0 ? (
        <p className="meta-text">Waiting for forwarding events…</p>
      ) : (
        <div className="event-list">
          {events.map((ev, i) => (
            <div key={i} className={`event-item ${ev.status}`}>
              <span className="event-time">{formatTime(ev.timestamp)}</span>
              <span className={`badge badge-${ev.status}`}>{ev.status}</span>
              <span className="event-detail">
                Rule {ev.rule_id} · {ev.content_type} · msg {ev.source_msg_id}
                {ev.status === 'success' && ev.target_msg_id && ` → ${ev.target_msg_id}`}
                {ev.error && <span className="event-error"> · {ev.error}</span>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
