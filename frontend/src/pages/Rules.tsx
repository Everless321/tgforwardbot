import { useState, useEffect, useCallback, useMemo, useRef, type FormEvent } from 'react'
import {
  fetchRules, createRule, updateRule, deleteRule, fetchChannels,
  startSync, stopSync,
  type Rule, type TgChannel,
} from '../api/client'
import SearchableSelect from '../components/SearchableSelect'

export default function Rules() {
  const [rules, setRules] = useState<Rule[]>([])
  const [channels, setChannels] = useState<TgChannel[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sourceId, setSourceId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [loadingChannels, setLoadingChannels] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const channelMap = new Map(channels.map(c => [c.id, c]))

  const hasSyncing = rules.some(r => r.sync_status === 'syncing')

  const channelOptions = useMemo(() =>
    channels.map(ch => ({
      value: String(ch.id),
      label: `${ch.title}${ch.username ? ` (@${ch.username})` : ''}`,
      icon: ch.type === 'channel' ? '📢' : '👥',
    })),
    [channels],
  )

  const load = useCallback(async () => {
    try {
      const [rulesData, channelsData] = await Promise.all([fetchRules(), fetchChannels()])
      setRules(rulesData)
      setChannels(channelsData)
      setError(null)
    } catch {
      setError('加载数据失败')
    } finally {
      setLoadingChannels(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (hasSyncing) {
      pollRef.current = setInterval(async () => {
        try {
          const rulesData = await fetchRules()
          setRules(rulesData)
        } catch { /* ignore */ }
      }, 3000)
    } else if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [hasSyncing])

  const handleRefreshChannels = async () => {
    setRefreshing(true)
    try {
      const channelsData = await fetchChannels(true)
      setChannels(channelsData)
    } catch {
      setError('刷新频道失败')
    } finally {
      setRefreshing(false)
    }
  }

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault()
    const src = parseInt(sourceId, 10)
    const tgt = parseInt(targetId, 10)
    if (!src || !tgt) return
    if (src === tgt) { setError('源频道和目标频道不能相同'); return }
    setSubmitting(true)
    try {
      await createRule({ source_chat_id: src, target_chat_id: tgt })
      setSourceId('')
      setTargetId('')
      await load()
    } catch {
      setError('创建规则失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggle = async (rule: Rule) => {
    try {
      await updateRule(rule.id, { enabled: !rule.enabled })
      await load()
    } catch {
      setError('更新规则失败')
    }
  }

  const handleDelete = async (rule: Rule) => {
    if (!window.confirm(`确认删除规则 #${rule.id}？`)) return
    try {
      await deleteRule(rule.id)
      await load()
    } catch {
      setError('删除规则失败')
    }
  }

  const handleSync = async (rule: Rule) => {
    try {
      if (rule.sync_status === 'syncing') {
        await stopSync(rule.id)
      } else {
        await startSync(rule.id)
      }
      await load()
    } catch {
      setError('同步操作失败')
    }
  }

  const channelLabel = (id: number) => {
    const ch = channelMap.get(id)
    return ch ? `${ch.title}` : `${id}`
  }

  const syncLabel = (rule: Rule) => {
    if (rule.sync_status === 'syncing') return `同步中… (${rule.synced_msg_count})`
    if (rule.sync_status === 'done') return `已完成 (${rule.synced_msg_count})`
    return '空闲'
  }

  return (
    <div className="page">
      <h1 className="page-title">转发规则</h1>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 className="section-title" style={{ margin: 0 }}>添加规则</h2>
          <button
            className="btn btn-sm"
            onClick={handleRefreshChannels}
            disabled={refreshing}
            style={{ whiteSpace: 'nowrap' }}
          >
            {refreshing ? '⏳ 刷新中…' : '🔄 刷新频道'}
          </button>
        </div>
        <form className="add-form" onSubmit={handleAdd}>
          <SearchableSelect
            options={channelOptions}
            value={sourceId}
            onChange={setSourceId}
            placeholder={loadingChannels ? '加载中…' : '源频道'}
            disabled={loadingChannels}
          />
          <span className="form-arrow">→</span>
          <SearchableSelect
            options={channelOptions}
            value={targetId}
            onChange={setTargetId}
            placeholder={loadingChannels ? '加载中…' : '目标频道'}
            disabled={loadingChannels}
          />
          <button className="btn btn-primary" type="submit" disabled={submitting || !sourceId || !targetId}>
            {submitting ? '添加中…' : '添加'}
          </button>
        </form>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-wrapper">
        <table className="table">
          <thead>
            <tr>
              <th>编号</th>
              <th>源频道</th>
              <th>目标频道</th>
              <th>状态</th>
              <th>同步</th>
              <th>消息数</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 ? (
              <tr><td colSpan={8} className="empty-cell">暂无转发规则</td></tr>
            ) : rules.map(rule => (
              <tr key={rule.id}>
                <td>#{rule.id}</td>
                <td>{channelLabel(rule.source_chat_id)}</td>
                <td>{channelLabel(rule.target_chat_id)}</td>
                <td>
                  <button
                    className={`toggle ${rule.enabled ? 'toggle-on' : 'toggle-off'}`}
                    onClick={() => handleToggle(rule)}
                  >
                    {rule.enabled ? '开启' : '关闭'}
                  </button>
                </td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="meta-text">{syncLabel(rule)}</span>
                    <button
                      className={`btn btn-sm ${rule.sync_status === 'syncing' ? 'btn-danger' : 'btn-primary'}`}
                      onClick={() => handleSync(rule)}
                    >
                      {rule.sync_status === 'syncing' ? '停止' : '同步'}
                    </button>
                  </div>
                </td>
                <td>{rule.message_count}</td>
                <td className="meta-text">{new Date(rule.created_at).toLocaleDateString('zh-CN')}</td>
                <td>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(rule)}>
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
