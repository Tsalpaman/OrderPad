// Tiny fetch wrapper: token handling + JSON + readable errors.
export function getSession() {
  try { return JSON.parse(localStorage.getItem('orderpad_session')) } 
  catch { return null }
}
export function setSession(s) {
  if (s) localStorage.setItem('orderpad_session', JSON.stringify(s))
  else localStorage.removeItem('orderpad_session')
}

export async function api(path, options = {}) {
  const session = getSession()
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
      ...options.headers,
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  })
  if (res.status === 401 && session && path !== '/api/login') {
    // token expired or account switched off mid-session
    setSession(null)
    location.href = '/'
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    const detail = data.detail
    const message = Array.isArray(detail)
      ? detail.map(d => d.msg || String(d)).join('; ')
      : (typeof detail === 'string' && detail)
          ? detail
          : `Request failed (${res.status})`
    throw new Error(message)
  }
  if (res.status === 204) return null
  return res.json()
}

export const euro = cents => (cents / 100).toFixed(2) + ' €'

export async function fetchVersion() {
  try {
    const res = await fetch('/api/version')
    return (await res.json()).version
  } catch {
    return null
  }
}

// Accent- and case-insensitive matching that also handles Greek:
// "ζαχαρη" matches "Ζάχαρη", "φρεντο" matches "Φρέντο", and ς == σ.
export const norm = s => (s || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replaceAll('ς', 'σ')
