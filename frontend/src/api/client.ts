export interface Rule {
  id: number
  source_chat_id: number
  target_chat_id: number
  enabled: boolean
  filters: Record<string, unknown> | null
  created_at: string
  message_count: number
}

export interface Message {
  id: number
  rule_id: number
  source_msg_id: number
  target_msg_id: number | null
  content_type: 'text' | 'photo' | 'video' | 'document' | 'audio' | 'voice' | 'sticker' | 'animation' | 'album' | 'other'
  status: 'pending' | 'success' | 'failed'
  error: string | null
  created_at: string
}

export interface MessageList {
  items: Message[]
  total: number
  page: number
  page_size: number
}

export interface Status {
  connected: boolean
  rules_count: number
  rules_active: number
  messages_today: number
  messages_failed_today: number
  last_forward_at: string | null
}

export interface ForwardEvent {
  type: 'forward_result'
  rule_id: number
  source_msg_id: number
  target_msg_id: number | null
  status: 'success' | 'failed'
  content_type: string
  error: string | null
  timestamp: string
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (res.status === 204) return undefined as unknown as T
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
  return res.json() as Promise<T>
}

export const fetchRules = (): Promise<Rule[]> =>
  request<Rule[]>('/api/rules')

export const createRule = (body: {
  source_chat_id: number
  target_chat_id: number
  filters?: object
}): Promise<Rule> =>
  request<Rule>('/api/rules', { method: 'POST', body: JSON.stringify(body) })

export const updateRule = (
  id: number,
  body: { enabled?: boolean; filters?: object },
): Promise<Rule> =>
  request<Rule>(`/api/rules/${id}`, { method: 'PUT', body: JSON.stringify(body) })

export const deleteRule = (id: number): Promise<void> =>
  request<void>(`/api/rules/${id}`, { method: 'DELETE' })

export interface FetchMessagesParams {
  page?: number
  page_size?: number
  status?: 'success' | 'failed' | 'pending'
  rule_id?: number
}

export const fetchMessages = (params: FetchMessagesParams = {}): Promise<MessageList> => {
  const q = new URLSearchParams()
  if (params.page) q.set('page', String(params.page))
  if (params.page_size) q.set('page_size', String(params.page_size))
  if (params.status) q.set('status', params.status)
  if (params.rule_id) q.set('rule_id', String(params.rule_id))
  return request<MessageList>(`/api/messages?${q}`)
}

export const fetchStatus = (): Promise<Status> =>
  request<Status>('/api/status')
