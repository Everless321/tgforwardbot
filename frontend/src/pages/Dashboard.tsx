import { useState, useEffect, useCallback } from 'react'
import { fetchStatus, type Status, type ForwardEvent } from '../api/client'
import { useWebSocket } from '../hooks/useWebSocket'

const MAX_EVENTS = 20

const CONTENT_TYPE_LABEL: Record<string, string> = {
  text: '文本', photo: '图片', video: '视频', document: '文件',
  audio: '音频', voice: '语音', sticker: '贴纸', animation: '动图',
  album: '相册', other: '其他',
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })
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
      setError('加载状态失败')
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
      <h1 className="page-title">仪表盘</h1>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">连接状态</div>
          <div className="stat-value">
            <span className={`dot ${status?.connected ? 'dot-green' : 'dot-red'}`} />
            {status?.connected ? '已连接' : '已断开'}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">活跃规则</div>
          <div className="stat-value">{status?.rules_active ?? '—'} / {status?.rules_count ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">今日转发</div>
          <div className="stat-value success">{status?.messages_today ?? '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">今日失败</div>
          <div className="stat-value danger">{status?.messages_failed_today ?? '—'}</div>
        </div>
      </div>

      {status?.last_forward_at && (
        <p className="meta-text">
          最近转发：{new Date(status.last_forward_at).toLocaleString('zh-CN')}
        </p>
      )}

      <h2 className="section-title">实时事件</h2>
      {events.length === 0 ? (
        <p className="meta-text">等待转发事件…</p>
      ) : (
        <div className="event-list">
          {events.map((ev, i) => (
            <div key={i} className={`event-item ${ev.status}`}>
              <span className="event-time">{formatTime(ev.timestamp)}</span>
              <span className={`badge badge-${ev.status}`}>{ev.status === 'success' ? '成功' : '失败'}</span>
              <span className="event-detail">
                规则 {ev.rule_id} · {CONTENT_TYPE_LABEL[ev.content_type] || ev.content_type} · 消息 {ev.source_msg_id}
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
