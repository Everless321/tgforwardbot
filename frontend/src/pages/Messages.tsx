import { useState, useEffect, useCallback } from 'react'
import { fetchMessages, type Message, type MessageList } from '../api/client'

type StatusFilter = '' | 'success' | 'failed' | 'pending'

const PAGE_SIZE = 20

export default function Messages() {
  const [data, setData] = useState<MessageList | null>(null)
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('')
  const [ruleIdFilter, setRuleIdFilter] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const params: Parameters<typeof fetchMessages>[0] = { page, page_size: PAGE_SIZE }
      if (statusFilter) params.status = statusFilter
      if (ruleIdFilter) params.rule_id = parseInt(ruleIdFilter, 10)
      const result = await fetchMessages(params)
      setData(result)
      setError(null)
    } catch {
      setError('Failed to load messages')
    }
  }, [page, statusFilter, ruleIdFilter])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const timer = setInterval(load, 10000)
    return () => clearInterval(timer)
  }, [load])

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1

  const handleFilterChange = (newStatus: StatusFilter, newRuleId: string) => {
    setStatusFilter(newStatus)
    setRuleIdFilter(newRuleId)
    setPage(1)
  }

  return (
    <div className="page">
      <h1 className="page-title">Messages</h1>

      <div className="filter-bar">
        <select
          className="input select"
          value={statusFilter}
          onChange={e => handleFilterChange(e.target.value as StatusFilter, ruleIdFilter)}
        >
          <option value="">All Statuses</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="pending">Pending</option>
        </select>
        <input
          className="input"
          type="number"
          placeholder="Filter by Rule ID"
          value={ruleIdFilter}
          onChange={e => handleFilterChange(statusFilter, e.target.value)}
        />
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-wrapper">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Rule</th>
              <th>Source Msg</th>
              <th>Target Msg</th>
              <th>Type</th>
              <th>Status</th>
              <th>Error</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {!data || data.items.length === 0 ? (
              <tr><td colSpan={8} className="empty-cell">No messages found</td></tr>
            ) : data.items.map((msg: Message) => (
              <tr key={msg.id}>
                <td>#{msg.id}</td>
                <td>#{msg.rule_id}</td>
                <td className="mono">{msg.source_msg_id}</td>
                <td className="mono">{msg.target_msg_id ?? '—'}</td>
                <td><span className="type-badge">{msg.content_type}</span></td>
                <td><span className={`badge badge-${msg.status}`}>{msg.status}</span></td>
                <td className="error-cell">{msg.error ?? '—'}</td>
                <td className="meta-text">{new Date(msg.created_at).toLocaleTimeString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data && data.total > 0 && (
        <div className="pagination">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            ← Prev
          </button>
          <span className="page-info">Page {page} / {totalPages} · {data.total} total</span>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
