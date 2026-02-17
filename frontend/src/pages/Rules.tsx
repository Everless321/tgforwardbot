import { useState, useEffect, useCallback, type FormEvent } from 'react'
import { fetchRules, createRule, updateRule, deleteRule, type Rule } from '../api/client'

export default function Rules() {
  const [rules, setRules] = useState<Rule[]>([])
  const [error, setError] = useState<string | null>(null)
  const [sourceId, setSourceId] = useState('')
  const [targetId, setTargetId] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await fetchRules()
      setRules(data)
      setError(null)
    } catch {
      setError('Failed to load rules')
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleAdd = async (e: FormEvent) => {
    e.preventDefault()
    const src = parseInt(sourceId, 10)
    const tgt = parseInt(targetId, 10)
    if (!src || !tgt) return
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

  return (
    <div className="page">
      <h1 className="page-title">Rules</h1>

      <div className="card">
        <h2 className="section-title">Add Rule</h2>
        <form className="add-form" onSubmit={handleAdd}>
          <input
            className="input"
            type="number"
            placeholder="Source Chat ID"
            value={sourceId}
            onChange={e => setSourceId(e.target.value)}
            required
          />
          <input
            className="input"
            type="number"
            placeholder="Target Chat ID"
            value={targetId}
            onChange={e => setTargetId(e.target.value)}
            required
          />
          <button className="btn btn-primary" type="submit" disabled={submitting}>
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
              <th>Source Chat ID</th>
              <th>Target Chat ID</th>
              <th>Enabled</th>
              <th>Messages</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 ? (
              <tr><td colSpan={7} className="empty-cell">No rules configured</td></tr>
            ) : rules.map(rule => (
              <tr key={rule.id}>
                <td>#{rule.id}</td>
                <td className="mono">{rule.source_chat_id}</td>
                <td className="mono">{rule.target_chat_id}</td>
                <td>
                  <button
                    className={`toggle ${rule.enabled ? 'toggle-on' : 'toggle-off'}`}
                    onClick={() => handleToggle(rule)}
                  >
                    {rule.enabled ? 'ON' : 'OFF'}
                  </button>
                </td>
                <td>{rule.message_count}</td>
                <td className="meta-text">{new Date(rule.created_at).toLocaleDateString()}</td>
                <td>
                  <button
                    className="btn btn-danger btn-sm"
                    onClick={() => handleDelete(rule)}
                  >
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
