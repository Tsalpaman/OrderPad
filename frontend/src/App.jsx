import { useEffect, useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { fetchVersion, getSession, setSession } from './api.js'
import Login from './views/Login.jsx'
import Tables from './views/Tables.jsx'
import Order from './views/Order.jsx'
import Kitchen from './views/Kitchen.jsx'
import Admin from './views/Admin.jsx'

function Shell({ children }) {
  const session = getSession()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const logout = () => { setSession(null); navigate('/') }
  const [version, setVersion] = useState(null)
  useEffect(() => { fetchVersion().then(setVersion) }, [])
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">
          Order<b>Pad</b>
          {version && <em className="version">v{version}</em>}
        </span>
        <nav>
          <Link className={pathname.startsWith('/tables') ? 'on' : ''} to="/tables">Tables</Link>
          {['admin', 'bar'].includes(session?.user.role) && (
            <Link className={pathname === '/kitchen' ? 'on' : ''} to="/kitchen">Bar</Link>
          )}
          {session?.user.role === 'admin' && (
            <Link className={pathname === '/admin' ? 'on' : ''} to="/admin">Admin</Link>
          )}
        </nav>
        <button className="ghost" onClick={logout}>{session?.user.name} · exit</button>
      </header>
      {children}
    </div>
  )
}

function Protected({ children, admin = false, roles = null }) {
  const session = getSession()
  if (!session) return <Navigate to="/" replace />
  const allowed = roles || (admin ? ['admin'] : null)
  if (allowed && !allowed.includes(session.user.role))
    return <Navigate to="/tables" replace />
  return <Shell>{children}</Shell>
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/tables" element={<Protected><Tables /></Protected>} />
      <Route path="/order/:tableId" element={<Protected><Order /></Protected>} />
      <Route path="/kitchen" element={<Protected roles={['admin', 'bar']}><Kitchen /></Protected>} />
      <Route path="/admin" element={<Protected admin><Admin /></Protected>} />
    </Routes>
  )
}
