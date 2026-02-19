import { useState, useEffect, useCallback } from 'react'
import { fetchMessages, type Message, type MessageList } from '../api/client'

type StatusFilter = '' | 'success' | 'failed' | 'pending'

const PAGE_SIZE = 20

const CONTENT_TYPE_LABEL: Record<string, string> = {
  text: '文本', photo: '图片', video: '视频', document: '文件',
  audio: '音频', voice: '语音', sticker: '贴纸', animation: '动图',
  album: '相册', other: '其他',
}

const STATUS_LABEL: Record<string, string> = {
  success: '成功', failed: '失败', pending: '等待中',
}

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
      setError('加载消息失败')
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
      <h1 className="page-title">消息记录</h1>

      <div className="filter-bar">
        <select
          className="input select"
          value={statusFilter}
          onChange={e => handleFilterChange(e.target.value as StatusFilter, ruleIdFilter)}
        >
          <option value="">全部状态</option>
          <option value="success">成功</option>
          <option value="failed">失败</option>
          <option value="pending">等待中</option>
        </select>
        <input
          className="input"
          type="number"
          placeholder="按规则 ID 筛选"
          value={ruleIdFilter}
          onChange={e => handleFilterChange(statusFilter, e.target.value)}
        />
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-wrapper">
        <table className="table">
          <thead>
            <tr>
              <th>编号</th>
              <th>规则</th>
              <th>内容</th>
              <th>类型</th>
              <th>状态</th>
              <th>错误</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            {!data || data.items.length === 0 ? (
              <tr><td colSpan={7} className="empty-cell">暂无消息记录</td></tr>
            ) : data.items.map((msg: Message) => (
              <tr key={msg.id}>
                <td>#{msg.id}</td>
                <td>#{msg.rule_id}</td>
                <td className="preview-cell" title={msg.text_preview ?? ''}>
                  {msg.text_preview
                    ? (msg.text_preview.length > 40 ? msg.text_preview.slice(0, 40) + '…' : msg.text_preview)
                    : <span className="meta-text">—</span>
                  }
                </td>
                <td><span className="type-badge">{CONTENT_TYPE_LABEL[msg.content_type] || msg.content_type}</span></td>
                <td><span className={`badge badge-${msg.status}`}>{STATUS_LABEL[msg.status] || msg.status}</span></td>
                <td className="error-cell">{msg.error ?? '—'}</td>
                <td className="meta-text">{new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour12: false })}</td>
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
            ← 上一页
          </button>
          <span className="page-info">第 {page} / {totalPages} 页 · 共 {data.total} 条</span>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            下一页 →
          </button>
        </div>
      )}
    </div>
  )
}
