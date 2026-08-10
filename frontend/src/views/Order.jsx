import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, euro, norm } from '../api.js'

// ---- options bottom-sheet -------------------------------------------------
function OptionSheet({ product, onConfirm, onClose }) {
  const [picked, setPicked] = useState(() => {
    const init = {}
    for (const g of product.option_groups) {
      const defaults = g.options.filter(o => o.is_default).map(o => o.id)
      init[g.id] = g.selection === 'single'
        ? (defaults[0] ?? null)
        : new Set(defaults)
    }
    return init
  })

  const toggle = (group, option) => setPicked(p => {
    const next = { ...p }
    if (group.selection === 'single') {
      next[group.id] = p[group.id] === option.id && !group.required
        ? null : option.id
    } else {
      const set = new Set(p[group.id])
      set.has(option.id) ? set.delete(option.id) : set.add(option.id)
      next[group.id] = set
    }
    return next
  })

  const isOn = (group, option) => group.selection === 'single'
    ? picked[group.id] === option.id
    : picked[group.id].has(option.id)

  const chosen = useMemo(() => {
    const ids = []
    for (const g of product.option_groups) {
      if (g.selection === 'single') { if (picked[g.id]) ids.push(picked[g.id]) }
      else ids.push(...picked[g.id])
    }
    const all = product.option_groups.flatMap(g => g.options)
    return ids.map(id => all.find(o => o.id === id))
  }, [picked, product])

  const missing = product.option_groups.filter(g =>
    g.required && g.selection === 'single' && !picked[g.id])

  const unit = product.price_cents +
    chosen.reduce((s, o) => s + o.price_delta_cents, 0)

  return (
    <div className="backdrop" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <header className="sheet-head">
          <b>{product.name}</b>
          <button className="ghost" onClick={onClose}>&times;</button>
        </header>
        {product.option_groups.map(g => (
          <div key={g.id} className="group-block">
            <div className="group-title">
              {g.name}
              {g.required && <span className="req">required</span>}
              {g.selection === 'multi' && <span className="hint small"> pick any</span>}
            </div>
            <div className="chips">
              {g.options.map(o => (
                <button key={o.id}
                  className={isOn(g, o) ? 'chip on' : 'chip'}
                  onClick={() => toggle(g, o)}>
                  {o.name}
                  {o.price_delta_cents > 0 && (
                    <em> +{euro(o.price_delta_cents)}</em>
                  )}
                </button>
              ))}
            </div>
          </div>
        ))}
        <button className="cta" disabled={missing.length > 0}
          onClick={() => onConfirm(chosen)}>
          {missing.length > 0
            ? `Pick ${missing[0].name.toLowerCase()} first`
            : `Add · ${euro(unit)}`}
        </button>
      </div>
    </div>
  )
}

// ---- order screen ----------------------------------------------------------
export default function Order() {
  const { tableId } = useParams()
  const navigate = useNavigate()
  const [catalog, setCatalog] = useState([])
  const [activeCat, setActiveCat] = useState(0)
  const [query, setQuery] = useState('')
  const [cart, setCart] = useState([]) // {product, options[], qty, note, showNote}
  const [sheet, setSheet] = useState(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  const [tables, setTables] = useState([])
  const [areas, setAreas] = useState([])
  const [activeOrders, setActiveOrders] = useState([])  // whole floor

  const refreshActive = () =>
    api('/api/orders?active=1').then(setActiveOrders).catch(console.error)

  useEffect(() => {
    api('/api/catalog').then(setCatalog).catch(console.error)
    api('/api/tables').then(setTables).catch(console.error)
    api('/api/areas').then(setAreas).catch(console.error)
    refreshActive()
  }, [tableId])

  const tableInfo = tables.find(t => t.id === Number(tableId)) || null
  const tab = activeOrders.filter(o => o.table.id === Number(tableId))
  const busyIds = new Set(activeOrders.map(o => o.table.id))
  const mergeable = tables.filter(
    t => busyIds.has(t.id) && t.id !== Number(tableId))

  const tabTotal = tab.reduce((sum, o) => sum + o.total_cents, 0)
  const clock = iso => new Date(iso)
    .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  const moveTable = async toId => {
    if (Number(toId) === Number(tableId)) return
    const target = tables.find(t => t.id === Number(toId))
    const label = target
      ? `${target.area_name ? target.area_name + ' · ' : ''}${target.name}`
      : 'that table'
    const hasOrder = tab.length > 0 || cart.length > 0
    if (hasOrder && !confirm(`Move this order to ${label}?`)) return
    try {
      if (tab.length > 0) {  // sent rounds move on the server
        await api(`/api/tables/${tableId}/transfer`,
          { method: 'POST', body: { table_id: Number(toId) } })
      }
      // The in-progress cart survives this navigation (same component,
      // new table id), so the WHOLE order follows the customer.
      navigate(`/order/${toId}`)
    } catch (e) { setError(e.message) }
  }

  const refreshTab = refreshActive

  const cancelRound = async order => {
    if (!confirm(`Cancel this round (${euro(order.total_cents)})?`)) return
    try {
      await api(`/api/orders/${order.id}`, { method: 'DELETE' })
      refreshTab()
    } catch (e) { setError(e.message) }
  }

  const cancelTab = async () => {
    if (!confirm(`Cancel the WHOLE open tab (${euro(tabTotal)})?`)) return
    try {
      await api(`/api/tables/${tableId}/cancel`, { method: 'POST' })
      navigate('/tables')
    } catch (e) { setError(e.message) }
  }

  const mergeFrom = async fromId => {
    if (!fromId) return
    const source = tables.find(t => t.id === Number(fromId))
    const label = source
      ? `${source.area_name ? source.area_name + ' · ' : ''}${source.name}`
      : 'that table'
    if (!confirm(`Merge ${label} into this table? Its open orders move here.`)) return
    try {
      await api(`/api/tables/${fromId}/transfer`,
        { method: 'POST', body: { table_id: Number(tableId) } })
      refreshActive()
    } catch (e) { setError(e.message) }
  }

  const settleTable = async () => {
    if (!confirm(`Settle ${tableInfo?.name || 'table'} · ${euro(tabTotal)}?`)) return
    try {
      await api(`/api/tables/${tableId}/settle`, { method: 'POST' })
      navigate('/tables')
    } catch (e) { setError(e.message) }
  }

  const lineKey = (product, options, note) =>
    [product.id, options.map(o => o.id).sort().join('-'), note].join('|')

  const addLine = (product, options) => setCart(cart => {
    const key = lineKey(product, options, '')
    const hit = cart.find(l => lineKey(l.product, l.options, l.note) === key)
    if (hit) return cart.map(l => l === hit ? { ...l, qty: l.qty + 1 } : l)
    return [...cart, { product, options, qty: 1, note: '', showNote: false }]
  })

  const tap = product => product.option_groups?.length
    ? setSheet(product)
    : addLine(product, [])

  const bump = (line, delta) => setCart(cart =>
    cart.map(l => l === line ? { ...l, qty: l.qty + delta } : l)
        .filter(l => l.qty > 0))

  const patchLine = (line, patch) => setCart(cart =>
    cart.map(l => l === line ? { ...l, ...patch } : l))

  const unitPrice = line => line.product.price_cents +
    line.options.reduce((s, o) => s + o.price_delta_cents, 0)

  const total = useMemo(() =>
    cart.reduce((sum, l) => sum + unitPrice(l) * l.qty, 0), [cart])

  const send = async () => {
    setSending(true); setError('')
    try {
      await api('/api/orders', { method: 'POST', body: {
        table_id: Number(tableId),
        items: cart.map(l => ({
          product_id: l.product.id, qty: l.qty, note: l.note,
          option_ids: l.options.map(o => o.id),
        })),
      }})
      navigate('/tables')
    } catch (e) { setError(e.message); setSending(false) }
  }

  const searching = query.trim().length > 0
  const visibleProducts = searching
    ? catalog.flatMap(c => c.products)
        .filter(p => norm(p.name).includes(norm(query)))
    : (catalog[activeCat]?.products || [])

  return (
    <main className="order-screen">
      <section className="menu">
        <input className="search" placeholder="Search all products&hellip;"
          value={query} onChange={e => setQuery(e.target.value)} />
        {!searching && (
          <div className="cat-tabs">
            {catalog.map((c, i) => (
              <button key={c.id} className={i === activeCat ? 'tab on' : 'tab'}
                onClick={() => setActiveCat(i)}>{c.name}</button>
            ))}
          </div>
        )}
        <div className="grid products">
          {searching && visibleProducts.length === 0 && (
            <p className="hint">No products match.</p>
          )}
          {visibleProducts.map(p => (
            <button key={p.id} className="tile product" onClick={() => tap(p)}>
              <span className="tile-name">{p.name}</span>
              <span className="price">{euro(p.price_cents)}</span>
            </button>
          ))}
        </div>
      </section>

      <aside className="receipt">
        <div className="receipt-head">
          <select className="table-switch" value={tableId}
            title="Move this order to another table"
            onChange={e => moveTable(e.target.value)}>
            {areas.map(a => (
              <optgroup key={a.id} label={a.name}>
                {tables.filter(t => t.area_id === a.id).map(t => (
                  <option key={t.id} value={t.id}>
                    {a.name} · {t.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
        {tab.length > 0 && (
          <details className="open-tab">
            <summary>
              Open tab · {euro(tabTotal)}
              <span className="hint small">
                {' '}({tab.length} {tab.length === 1 ? 'round' : 'rounds'})
              </span>
            </summary>
            {tab.map(o => (
              <div key={o.id} className="round">
                <div className="round-head">
                  {clock(o.created_at)} · {o.waiter}
                  <button className="x round-x" title="Cancel this round"
                    onMouseDown={e => { e.preventDefault(); cancelRound(o) }}>
                    &times;
                  </button>
                </div>
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
            <div className="tab-actions">
              <button className="ghost danger" onClick={cancelTab}>
                Cancel tab
              </button>
              <button className="cta small" onClick={settleTable}>
                Settle · {euro(tabTotal)}
              </button>
            </div>
          </details>
        )}
        {mergeable.length > 0 && (
          <div className="merge-row">
            <span className="hint small">Merge table here:</span>
            <select className="move-select" value=""
              onChange={e => mergeFrom(e.target.value)}>
              <option value="" disabled>choose&hellip;</option>
              {areas.map(a => (
                <optgroup key={a.id} label={a.name}>
                  {mergeable.filter(t => t.area_id === a.id).map(t => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
        )}
        {cart.length === 0 && <p className="hint">Tap products to add them.</p>}
        {cart.map((line, i) => (
          <div key={i} className="line">
            <div className="line-main">
              <span className="line-name">{line.product.name}</span>
              <span className="line-qty">
                <button onClick={() => bump(line, -1)}>-</button>
                <b>{line.qty}</b>
                <button onClick={() => bump(line, +1)}>+</button>
              </span>
              <span className="line-sum">{euro(unitPrice(line) * line.qty)}</span>
            </div>
            {line.options.length > 0 && (
              <div className="line-opts">
                {line.options.map(o => o.name).join(', ')}
              </div>
            )}
            {line.note || line.showNote ? (
              <input className="note" placeholder="note for the bar" autoFocus
                value={line.note}
                onChange={e => patchLine(line, { note: e.target.value })} />
            ) : (
              <button className="note-toggle"
                onClick={() => patchLine(line, { showNote: true })}>+ note</button>
            )}
          </div>
        ))}
        <div className="receipt-total"><span>TOTAL</span><b>{euro(total)}</b></div>
        {error && <p className="error">{error}</p>}
        <button className="cta" disabled={cart.length === 0 || sending} onClick={send}>
          {sending ? 'Sending…' : 'Send to bar'}
        </button>
      </aside>

      {sheet && (
        <OptionSheet product={sheet}
          onClose={() => setSheet(null)}
          onConfirm={options => { addLine(sheet, options); setSheet(null) }} />
      )}
    </main>
  )
}
