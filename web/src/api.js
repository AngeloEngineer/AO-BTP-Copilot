const TOKEN_KEY = 'btma_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(t) {
  localStorage.setItem(TOKEN_KEY, t)
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

async function jreq(method, path, body, timeout = 20000) {
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeout)
  try {
    const res = await fetch(path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    })
    const data = res.status === 204 ? null : await res.json().catch(() => null)
    if (!res.ok) throw new Error((data && data.detail) || `Erreur ${res.status}`)
    return data
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  register: (body) => jreq('POST', '/api/auth/register', body),
  login: (body) => jreq('POST', '/api/auth/login', body),
  me: () => jreq('GET', '/api/auth/me'),
  meta: () => jreq('GET', '/api/meta'),
  consultations: () => jreq('GET', '/api/consultations'),
  conversations: () => jreq('GET', '/api/conversations'),
  createConversation: (titre = 'Nouvelle discussion') =>
    jreq('POST', '/api/conversations', { titre }),
  conversation: (id) => jreq('GET', `/api/conversations/${id}`),
  renameConversation: (id, titre) => jreq('PATCH', `/api/conversations/${id}`, { titre }),
  deleteConversation: (id) => jreq('DELETE', `/api/conversations/${id}`),
}

/** POST message + lecture du flux SSE (chat / résumé / checklist). */
export async function streamMessage(conversationId, content, marche, onEvent, signal) {
  const res = await fetch(`/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ content, marche }),
    signal,
  })
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => null)
    throw new Error((err && err.detail) || `Erreur ${res.status}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const raw = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      for (const line of raw.split('\n')) {
        if (line.startsWith('data:')) {
          try {
            onEvent(JSON.parse(line.slice(5).trim()))
          } catch {
            /* ignoré */
          }
        }
      }
    }
  }
}