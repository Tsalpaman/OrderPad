import { useEffect, useRef, useState } from 'react'
import { api, euro } from '../api.js'

export default function Kitchen() {
  const [orders, setOrders] = useState([])
  const [tables, setTables] = useState([])
  const [areas, setAreas] = useState([])
  const [live, setLive] = useState(false)
  const pending = useRef(new Set())

  const refetch = () =>
    api('/api/orders?active=1').then(setOrders).catch(console.error)

  useEffect(() => {
    refetch()
    api('/api/tables').then(setTables).catch(console.error)
    api('/api/areas').then(setAreas).catch(console.error)
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/kitchen`)
    ws.onopen = () => setLive(true)
    ws.onclose = () => setLive(false)
    ws.onmessage = e => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'order.created' || msg.type === 'order.updated') {
        setOrders(list => {
          const rest = list.filter(o => o.id !== msg.order.id)
          return ['paid', 'served'].includes(msg.order.status)
            ? rest : [...rest, msg.order]
        })
      }
      if (msg.type === 'table.settled' || msg.type === 'table.transferred') {
        refetch()
      }
    }
    const ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25000)
    return () => { clearInterval(ping); ws.close() }
  }, [])

  // One tab per table: group the open orders, sum the running total.
  const tabs = Object.values(orders.reduce((acc, o) => {
    const tab = acc[o.table.id] ??= { table: o.table, orders: [], total: 0 }
    tab.orders.push(o)
    tab.total += o.total_cents
    return acc
  }, {}))
    .map(tab => ({
      ...tab,
      orders: [...tab.orders].sort(
        (a, b) => a.created_at.localeCompare(b.created_at)),
    }))
    .sort((a, b) =>
      (a.table.area_name || '').localeCompare(b.table.area_name || '')
      || a.table.name.localeCompare(b.table.name, undefined,
                                    { numeric: true }))

  const age = iso => Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000))
  const clock = iso => new Date(iso)
    .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  const settle = async tab => {
    if (!confirm(`Settle ${tab.table.name} · ${euro(tab.total)}?`)) return
    const key = `settle-${tab.table.id}`
    if (pending.current.has(key)) return
    pending.current.add(key)
    setOrders(list => list.filter(o => o.table.id !== tab.table.id))
    try {
      await api(`/api/tables/${tab.table.id}/settle`, { method: 'POST' })
    } catch (e) {
      alert(e.message)
    } finally {
      pending.current.delete(key)
      refetch()
    }
  }

  const move = async (tab, toId) => {
    if (Number(toId) === tab.table.id) return
    try {
      await api(`/api/tables/${tab.table.id}/transfer`,
        { method: 'POST', body: { table_id: Number(toId) } })
      refetch()
    } catch (e) { alert(e.message) }
  }

  return (
    <main className="kitchen">
      <div className="kitchen-bar">
        <h2>Open tables</h2>
        <span className={live ? 'pill live' : 'pill'}>{live ? 'LIVE' : 'offline'}</span>
      </div>
      {tabs.length === 0 && (
        <p className="hint">All clear. New orders appear here instantly.</p>
      )}
      <div className="grid cards">
        {tabs.map(tab => (
          <article key={tab.table.id} className="card">
            <header>
              <div className="tab-title">
                <span className="tab-area">{tab.table.area_name}</span>
                <select className="table-move" value={tab.table.id}
                  title="Move this tab to another table"
                  onChange={e => move(tab, e.target.value)}>
                {areas.map(a => (
                  <optgroup key={a.id} label={a.name}>
                    {tables.filter(t => t.area_id === a.id).map(t => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </optgroup>
                ))}
                {tables.some(t => !t.area_id) && (
                  <optgroup label="Other">
                    {tables.filter(t => !t.area_id).map(t => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </optgroup>
                )}
              </select>
              </div>
              <span>{age(tab.orders[0].created_at)} min open</span>
            </header>
            {tab.orders.map(o => (
              <div key={o.id} className="round">
                <div className="round-head">{clock(o.created_at)} · {o.waiter}</div>
                <ul>
                  {o.items.map((i, k) => (
                    <li key={k}>
                      <b>{i.qty}&times;</b> {i.name}
                      {i.options?.length > 0 && (
                        <span className="opts"> — {i.options.map(x => x.name).join(', ')}</span>
                      )}
                      {i.note && <em> - {i.note}</em>}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <footer>
              <span className="tab-total">{euro(tab.total)}</span>
              <button className="cta small" onClick={() => settle(tab)}>
                Settle
              </button>
            </footer>
          </article>
        ))}
      </div>
    </main>
  )
}
