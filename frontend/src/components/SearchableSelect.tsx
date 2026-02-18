import { useState, useRef, useEffect } from 'react'

interface Option {
  value: string
  label: string
  icon?: string
}

interface Props {
  options: Option[]
  value: string
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
}

export default function SearchableSelect({ options, value, onChange, placeholder = 'Select…', disabled }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = options.find(o => o.value === value)
  const filtered = options.filter(o =>
    o.label.toLowerCase().includes(query.toLowerCase())
  )

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus()
  }, [open])

  return (
    <div className={`ss-wrap ${disabled ? 'ss-disabled' : ''}`} ref={ref}>
      <div
        className={`ss-trigger ${open ? 'ss-open' : ''}`}
        onClick={() => { if (!disabled) setOpen(!open) }}
      >
        <span className={selected ? 'ss-value' : 'ss-placeholder'}>
          {selected ? `${selected.icon || ''} ${selected.label}` : placeholder}
        </span>
        <span className="ss-arrow">{open ? '▲' : '▼'}</span>
      </div>
      {open && (
        <div className="ss-dropdown">
          <input
            ref={inputRef}
            className="ss-search"
            type="text"
            placeholder="Search…"
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <div className="ss-list">
            {filtered.length === 0 ? (
              <div className="ss-empty">No matches</div>
            ) : filtered.map(o => (
              <div
                key={o.value}
                className={`ss-option ${o.value === value ? 'ss-selected' : ''}`}
                onClick={() => { onChange(o.value); setOpen(false); setQuery('') }}
              >
                {o.icon && <span className="ss-icon">{o.icon}</span>}
                {o.label}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
