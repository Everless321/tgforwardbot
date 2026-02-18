import { useState, useEffect, useRef } from 'react'
import { fetchLogs, type LogEntry } from '../api/client'

const LEVEL_COLORS: Record<string, string> = {
  INFO: 'var(--accent)',
  WARNING: 'var(--warning)',
  ERROR: 'var(--danger)',
  DEBUG: 'var(--text-secondary)',
}

export default function Logs() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [filter, setFilter] = useState<string | undefined>()
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const data = await fetchLogs(500, filter)
        if (active) setLogs(data)
      } catch {}
    }
    load()
    const timer = setInterval(load, 3000)
    return () => { active = false; clearInterval(timer) }
  }, [filter])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const filters = [
    { label: 'All', value: undefined },
    { label: 'INFO', value: 'INFO' },
    { label: 'WARN', value: 'WARNING' },
    { label: 'ERROR', value: 'ERROR' },
  ]

  const formatTime = (ts: string) => {
    try {
      return new Date(ts).toLocaleTimeString('en-GB', { hour12: false })
    } catch {
      return ts
    }
  }

  return (
    <div className="page">
      <h1 className="page-title">Logs</h1>
      <div className="log-filters">
        {filters.map(f => (
          <button
            key={f.label}
            className={`btn btn-sm ${filter === f.value ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>
      <div className="log-container" ref={containerRef}>
        {logs.length === 0 ? (
          <div className="log-empty">No logs</div>
        ) : (
          logs.map((entry, i) => (
            <div key={i} className="log-entry">
              <span className="log-time">{formatTime(entry.timestamp)}</span>
              <span className="log-level" style={{ color: LEVEL_COLORS[entry.level] || 'var(--text-secondary)' }}>
                {entry.level}
              </span>
              <span className="log-msg">{entry.message}</span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
