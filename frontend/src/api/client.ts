export interface Rule {
  id: number
  source_chat_id: number
  target_chat_id: number
  enabled: boolean
  filters: Record<string, unknown> | null
  sync_status: 'idle' | 'syncing' | 'done'
  synced_msg_count: number
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

export interface AuthUser {
  phone: string
  first_name: string
  username: string | null
}

export interface AuthStatus {
  authorized: boolean
  user: AuthUser | null
}

export interface AuthActionResult {
  status: string
  user: AuthUser | null
}

const TOKEN_KEY = 'token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(path, { headers, ...options })
  if (res.status === 401) {
    clearToken()
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (res.status === 204) return undefined as unknown as T
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`)
  return res.json() as Promise<T>
}

export interface TgChannel {
  id: number
  title: string
  type: 'channel' | 'group'
  username: string | null
}

export const fetchChannels = (refresh = false): Promise<TgChannel[]> =>
  request<TgChannel[]>(`/api/channels/${refresh ? '?refresh=true' : ''}`)

export const fetchRules = (): Promise<Rule[]> =>
  request<Rule[]>('/api/rules/')

export const createRule = (body: {
  source_chat_id: number
  target_chat_id: number
  filters?: object
}): Promise<Rule> =>
  request<Rule>('/api/rules/', { method: 'POST', body: JSON.stringify(body) })

export const updateRule = (
  id: number,
  body: { enabled?: boolean; filters?: object },
): Promise<Rule> =>
  request<Rule>(`/api/rules/${id}`, { method: 'PUT', body: JSON.stringify(body) })

export const deleteRule = (id: number): Promise<void> =>
  request<void>(`/api/rules/${id}`, { method: 'DELETE' })

export const startSync = (id: number): Promise<{ status: string; rule_id: number }> =>
  request(`/api/rules/${id}/sync`, { method: 'POST' })

export const stopSync = (id: number): Promise<{ status: string; rule_id: number }> =>
  request(`/api/rules/${id}/sync/stop`, { method: 'POST' })

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

export const fetchAuthStatus = (): Promise<AuthStatus> =>
  request<AuthStatus>('/api/auth/status')

export const sendCode = (phone: string): Promise<AuthActionResult> =>
  request<AuthActionResult>('/api/auth/send-code', { method: 'POST', body: JSON.stringify({ phone }) })

export const verifyCode = (code: string): Promise<AuthActionResult> =>
  request<AuthActionResult>('/api/auth/verify', { method: 'POST', body: JSON.stringify({ code }) })

export const verify2FA = (password: string): Promise<AuthActionResult> =>
  request<AuthActionResult>('/api/auth/2fa', { method: 'POST', body: JSON.stringify({ password }) })

export const logout = (): Promise<AuthActionResult> =>
  request<AuthActionResult>('/api/auth/logout', { method: 'POST' })

export const login = async (password: string): Promise<void> => {
  const res = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: '登录失败' }))
    throw new Error(data.detail || '登录失败')
  }
  const data = await res.json()
  setToken(data.access_token)
}
