import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, fetchVersion, setSession } from '../api.js'

export default function Login() {
  const [version, setVersion] = useState(null)
  useEffect(() => { fetchVersion().then(setVersion) }, [])
  const [pin, setPin] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const press = d => { setError(''); if (pin.length < 8) setPin(pin + d) }

  const submit = async () => {
    if (pin.length < 4) { setError('PIN is 4-8 digits'); return }
    try {
      const session = await api('/api/login', { method: 'POST', body: { pin } })
      setSession(session)
      const home = { admin: '/admin', bar: '/kitchen' }[session.user.role]
      navigate(home || '/tables')
    } catch (e) { setError(e.message); setPin('') }
  }

  return (
    <div className="login">
      <div className="brand big">Order<b>Pad</b></div>
      <p className="hint">Enter your PIN</p>
      <div className="dots">
        {[...Array(8)].map((_, i) => (
          <span key={i} className={i < pin.length ? 'dot full' : 'dot'} />
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      <div className="keypad">
        {['1','2','3','4','5','6','7','8','9','C','0','GO'].map(k => (
          <button key={k}
            className={k === 'GO' ? 'key go' : k === 'C' ? 'key clear' : 'key'}
            onClick={() => k === 'GO' ? submit() : k === 'C' ? setPin('') : press(k)}>
            {k === 'GO' ? '→' : k}
          </button>
        ))}
      </div>
      <p className="hint small">demo PINs - waiter 1111 · barman 2222 · admin 9999</p>
      {version && <p className="hint small">OrderPad v{version}</p>}
    </div>
  )
}
