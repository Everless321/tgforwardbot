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
      setError('Failed to load data')
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
      setError('Failed to refresh channels')
    } finally {
      setRefreshing(false)
    }
  }

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault()
    const src = parseInt(sourceId, 10)
    const tgt = parseInt(targetId, 10)
    if (!src || !tgt) return
    if (src === tgt) { setError('Source and target cannot be the same'); return }
    setSubmitting(true)
    try {
      await createRule({ source_chat_id: src, target_chat_id: tgt })
      setSourceId('')
      setTargetId('')
      await load()
    } catch {
      setError('Failed to create rule')
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggle = async (rule: Rule) => {
    try {
      await updateRule(rule.id, { enabled: !rule.enabled })
      await load()
    } catch {
      setError('Failed to update rule')
    }
  }

  const handleDelete = async (rule: Rule) => {
    if (!window.confirm(`Delete rule #${rule.id}?`)) return
    try {
      await deleteRule(rule.id)
      await load()
    } catch {
      setError('Failed to delete rule')
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
      setError('Failed to toggle sync')
    }
  }

  const channelLabel = (id: number) => {
    const ch = channelMap.get(id)
    return ch ? `${ch.title}` : `${id}`
  }

  const syncLabel = (rule: Rule) => {
    if (rule.sync_status === 'syncing') return `Syncing… (${rule.synced_msg_count})`
    if (rule.sync_status === 'done') return `Done (${rule.synced_msg_count})`
    return 'Idle'
  }

  return (
    <div className="page">
      <h1 className="page-title">Rules</h1>

      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 className="section-title" style={{ margin: 0 }}>Add Rule</h2>
          <button
            className="btn btn-sm"
            onClick={handleRefreshChannels}
            disabled={refreshing}
            style={{ whiteSpace: 'nowrap' }}
          >
            {refreshing ? '⏳ Refreshing…' : '🔄 Refresh Channels'}
          </button>
        </div>
        <form className="add-form" onSubmit={handleAdd}>
          <SearchableSelect
            options={channelOptions}
            value={sourceId}
            onChange={setSourceId}
            placeholder={loadingChannels ? 'Loading…' : 'Source channel'}
            disabled={loadingChannels}
          />
          <span className="form-arrow">→</span>
          <SearchableSelect
            options={channelOptions}
            value={targetId}
            onChange={setTargetId}
            placeholder={loadingChannels ? 'Loading…' : 'Target channel'}
            disabled={loadingChannels}
          />
          <button className="btn btn-primary" type="submit" disabled={submitting || !sourceId || !targetId}>
            {submitting ? 'Adding…' : 'Add Rule'}
          </button>
        </form>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="table-wrapper">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Source</th>
              <th>Target</th>
              <th>Enabled</th>
              <th>Sync</th>
              <th>Messages</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 ? (
              <tr><td colSpan={8} className="empty-cell">No rules configured</td></tr>
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
                    {rule.enabled ? 'ON' : 'OFF'}
                  </button>
                </td>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="meta-text">{syncLabel(rule)}</span>
                    <button
                      className={`btn btn-sm ${rule.sync_status === 'syncing' ? 'btn-danger' : 'btn-primary'}`}
                      onClick={() => handleSync(rule)}
                    >
                      {rule.sync_status === 'syncing' ? 'Stop' : 'Sync'}
                    </button>
                  </div>
                </td>
                <td>{rule.message_count}</td>
                <td className="meta-text">{new Date(rule.created_at).toLocaleDateString()}</td>
                <td>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(rule)}>
                    Delete
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
