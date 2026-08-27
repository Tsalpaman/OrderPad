import { useEffect, useRef, useState } from 'react'
import { api, euro, norm } from '../api.js'

// Fires on mousedown (before an input blur can re-render and eat the click).
const press = fn => e => { e.preventDefault(); fn() }

export default function Admin() {
  const [summary, setSummary] = useState(null)
  const [zReport, setZReport] = useState(null)
  const [products, setProducts] = useState([])
  const [catalog, setCatalog] = useState([])
  const [groups, setGroups] = useState([])
  const [draft, setDraft] = useState({ name: '', price: '', category_id: 1 })
  const [groupDraft, setGroupDraft] = useState(
    { name: '', selection: 'single', required: false })
  const [optionDrafts, setOptionDrafts] = useState({})
  const [catDraft, setCatDraft] = useState('')
  const [menuQuery, setMenuQuery] = useState('')
  const [users, setUsers] = useState([])
  const [staffDraft, setStaffDraft] = useState(
    { name: '', pin: '', role: 'waiter' })
  const [pinDrafts, setPinDrafts] = useState({})
  const [serverInfo, setServerInfo] = useState(null)
  const [panels, setPanels] = useState(null)

  // Prevents double-fired deletes (e.g. a stray second click before the
  // list re-renders) from re-targeting an id that's already gone and
  // surfacing a scary "not found" alert for something that actually worked.
  const pending = useRef(new Set())

  const reload = () => Promise.all([
    api('/api/summary'), api('/api/products'), api('/api/catalog'),
    api('/api/option-groups'), api('/api/reports/z'), api('/api/users'),
    api('/api/server-info'), api('/api/stats-settings'),
  ]).then(([s, p, c, g, z, u, srv, st]) => {
    setSummary(s); setProducts(p); setCatalog(c)
    setGroups(g); setZReport(z); setUsers(u); setServerInfo(srv)
    setPanels(st.panels)
  }).catch(console.error)

  useEffect(() => {
    reload()
    // Keep the numbers honest while the page sits open: refresh on every
    // kitchen event (new order, settle, transfer) and on window focus.
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/kitchen`)
    ws.onmessage = () => reload()
    const onFocus = () => reload()
    window.addEventListener('focus', onFocus)
    return () => { ws.close(); window.removeEventListener('focus', onFocus) }
  }, [])

  const guard = fn => async (...args) => {
    try { await fn(...args) } catch (e) { alert(e.message) }
  }

  // key: a unique id for the "in-flight" lock. optimistic: runs
  // synchronously to remove the item from local state right away.
  const safeDelete = async (key, path, optimistic) => {
    if (pending.current.has(key)) return
    pending.current.add(key)
    optimistic()
    try {
      await api(path, { method: 'DELETE' })
    } catch (e) {
      if (!/not found/i.test(e.message)) alert(e.message)
    } finally {
      pending.current.delete(key)
      reload()
    }
  }

  // ---- products ----
  const save = guard(async (product, patch) => {
    await api(`/api/products/${product.id}`, { method: 'PATCH', body: {
      name: product.name, price_cents: product.price_cents,
      category_id: product.category_id, active: product.active,
      option_group_ids: product.option_groups.map(g => g.id),
      ...patch,
    }})
    reload()
  })

  const toggleGroupOnProduct = (product, group) => {
    const ids = product.option_groups.map(g => g.id)
    const next = ids.includes(group.id)
      ? ids.filter(id => id !== group.id)
      : [...ids, group.id]
    save(product, { option_group_ids: next })
  }

  const create = guard(async () => {
    if (!draft.name || !draft.price) return
    await api('/api/products', { method: 'POST', body: {
      name: draft.name, price_cents: Math.round(Number(draft.price) * 100),
      category_id: Number(draft.category_id),
    }})
    setDraft({ name: '', price: '', category_id: draft.category_id })
    reload()
  })

  const deleteProduct = product => {
    if (!confirm(`Delete "${product.name}"?`)) return
    safeDelete(`product-${product.id}`, `/api/products/${product.id}`,
      () => setProducts(list => list.filter(p => p.id !== product.id)))
  }

  // ---- option groups ----
  const createGroup = guard(async () => {
    if (!groupDraft.name) return
    await api('/api/option-groups', { method: 'POST', body: groupDraft })
    setGroupDraft({ name: '', selection: 'single', required: false })
    reload()
  })

  const deleteGroup = group => {
    if (!confirm(`Delete option group "${group.name}"?`)) return
    safeDelete(`group-${group.id}`, `/api/option-groups/${group.id}`,
      () => setGroups(list => list.filter(g => g.id !== group.id)))
  }

  const patchGroup = guard(async (group, patch) => {
    await api(`/api/option-groups/${group.id}`, { method: 'PATCH', body: patch })
    reload()
  })

  const addOption = guard(async group => {
    const d = optionDrafts[group.id]
    if (!d?.name) return
    await api(`/api/option-groups/${group.id}/options`, { method: 'POST', body: {
      name: d.name,
      price_delta_cents: Math.round(Number(d.delta || 0) * 100),
    }})
    setOptionDrafts({ ...optionDrafts, [group.id]: { name: '', delta: '' } })
    reload()
  })

  const patchOption = guard(async (option, patch) => {
    await api(`/api/options/${option.id}`, { method: 'PATCH', body: patch })
    reload()
  })

  const deleteOption = (group, option) => {
    safeDelete(`option-${option.id}`, `/api/options/${option.id}`,
      () => setGroups(list => list.map(g => g.id !== group.id ? g : {
        ...g, options: g.options.filter(o => o.id !== option.id),
      })))
  }

  // ---- categories & tables ----
  const createNamed = guard(async (path, name, clear) => {
    if (!name.trim()) return
    await api(path, { method: 'POST', body: { name: name.trim() } })
    clear(''); reload()
  })

  const renameNamed = guard(async (path, name) => {
    await api(path, { method: 'PATCH', body: { name } })
    reload()
  })

  const moveItem = guard(async (path, direction) => {
    await api(path, { method: 'POST', body: { direction } })
    reload()
  })

  const togglePanel = guard(async key => {
    const next = { ...panels, [key]: !panels[key] }
    setPanels(next)  // optimistic: the switch responds instantly
    const saved = await api('/api/stats-settings',
      { method: 'PATCH', body: { panels: { [key]: next[key] } } })
    setPanels(saved.panels)
  })

  const createUser = guard(async () => {
    const { name, pin, role } = staffDraft
    if (!name.trim() || pin.length < 4) return
    await api('/api/users', { method: 'POST',
      body: { name: name.trim(), pin, role } })
    setStaffDraft({ name: '', pin: '', role: 'waiter' })
    reload()
  })

  const patchUser = guard(async (user, patch) => {
    await api(`/api/users/${user.id}`, { method: 'PATCH', body: patch })
    reload()
  })

  const setUserPin = user => {
    const pin = pinDrafts[user.id] || ''
    if (pin.length < 4) return
    patchUser(user, { pin })
    setPinDrafts({ ...pinDrafts, [user.id]: '' })
  }

  const deleteUser = user => {
    if (!confirm(`Delete ${user.name}?`)) return
    safeDelete(`user-${user.id}`, `/api/users/${user.id}`,
      () => setUsers(list => list.filter(x => x.id !== user.id)))
  }

  const deleteCategory = category => {
    if (!confirm(`Delete ${category.name}?`)) return
    safeDelete(`category-${category.id}`, `/api/categories/${category.id}`,
      () => setCatalog(list => list.filter(c => c.id !== category.id)))
  }

  return (
    <main className="admin">
      <section className="stats">
        <div className="stat"><b>{summary?.orders_today ?? '–'}</b><span>orders today</span></div>
        <div className="stat"><b>{summary ? euro(summary.revenue_cents_today) : '–'}</b><span>revenue today</span></div>
        <div className="stat top">
          <span>top sellers</span>
          <ol>{summary?.top_products.map(t => <li key={t.name}>{t.name} &times;{t.qty}</li>)}</ol>
        </div>
      </section>

      {serverInfo && (
        <section className="panel">
          <h3>Connect devices</h3>
          <p className="hint">
            Phones &amp; tablets on the shop WiFi open this address in
            their browser:
          </p>
          <div className="device-url">{serverInfo.url}</div>
          <p className="hint small">
            Then browser menu &rarr; "Add to Home screen" for a one-tap
            app icon. Requires the server started with
            start_orderpad.bat (single-server mode).
          </p>
        </section>
      )}

      <section className="panel z-print">
        <div className="panel-head">
          <h3>End of day &middot; Z report</h3>
          <button className="cta small no-print" onClick={() => window.print()}>
            Print Z
          </button>
        </div>
        <p className="hint small">{zReport?.date}</p>
        <table>
          <thead><tr><th>Waiter</th><th>Orders</th><th>Revenue</th></tr></thead>
          <tbody>
            {zReport?.waiters.map(w => (
              <tr key={w.waiter}>
                <td>{w.waiter}</td>
                <td>{w.orders}</td>
                <td>{euro(w.revenue_cents)}</td>
              </tr>
            ))}
            {zReport?.waiters.length === 0 && (
              <tr><td colSpan="3" className="hint">No orders yet today.</td></tr>
            )}
            <tr className="z-total">
              <td><b>TOTAL</b></td>
              <td><b>{zReport?.total_orders ?? 0}</b></td>
              <td><b>{zReport ? euro(zReport.total_revenue_cents) : '–'}</b></td>
            </tr>
          </tbody>
        </table>
      </section>

      {panels && (
        <section className="panel">
          <h3>Statistics panels</h3>
          <p className="hint small">
            Switch off anything you don't want on the Stats page. The
            setting is stored on the server, so it applies to every device.
          </p>
          <div className="panel-toggles">
            {[
              ['summary', 'Summary cards', 'Totals, average order, peak hour'],
              ['revenue_by_day', 'Revenue trend', 'Daily revenue, last 14 days'],
              ['by_hour', 'Busiest hours', 'Orders per hour of the day'],
              ['staff', 'Staff performance', 'Per-waiter sales metrics'],
              ['pareto', 'Pareto 80/20', 'Which products drive the revenue'],
              ['affinity', 'Sold together', 'Products bought in the same order'],
            ].map(([key, label, note]) => (
              <div key={key} className="toggle-row">
                <button className={panels[key] ? 'ghost on' : 'ghost'}
                  onClick={() => togglePanel(key)}>
                  {panels[key] ? 'on' : 'off'}
                </button>
                <span>
                  <b>{label}</b>
                  <span className="sub">{note}</span>
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="panel">
        <h3>Staff</h3>
        <div className="new-product">
          <input placeholder="Name" value={staffDraft.name}
            onChange={e => setStaffDraft({ ...staffDraft, name: e.target.value })} />
          <input placeholder="PIN (4-8 digits)" inputMode="numeric" maxLength="8"
            value={staffDraft.pin}
            onChange={e => setStaffDraft({ ...staffDraft,
              pin: e.target.value.replace(/\D/g, '') })} />
          <select value={staffDraft.role}
            onChange={e => setStaffDraft({ ...staffDraft, role: e.target.value })}>
            <option value="staff">staff</option>
            <option value="admin">admin</option>
          </select>
          <button className="cta small" onClick={createUser}>Add</button>
        </div>
        {users.map(u => (
          <div key={u.id} className={u.active ? 'opt-row' : 'opt-row off'}>
            <input className="mini wide" key={`sn${u.id}-${u.name}`}
              defaultValue={u.name}
              onBlur={e => e.target.value && e.target.value !== u.name
                && patchUser(u, { name: e.target.value })} />
            <select value={u.role}
              onChange={e => patchUser(u, { role: e.target.value })}>
              <option value="waiter">waiter</option>
              <option value="bar">barman</option>
              <option value="admin">admin</option>
            </select>
            <input className="mini" placeholder="new PIN" inputMode="numeric"
              maxLength="8" value={pinDrafts[u.id] || ''}
              onChange={e => setPinDrafts({ ...pinDrafts,
                [u.id]: e.target.value.replace(/\D/g, '') })}
              onBlur={() => setUserPin(u)} />
            <button className="ghost"
              onClick={() => patchUser(u, { active: !u.active })}>
              {u.active ? 'on' : 'off'}
            </button>
            <button className="x big"
              onMouseDown={press(() => deleteUser(u))}>&times;</button>
          </div>
        ))}
        <p className="hint small">
          "off" blocks login but keeps the person's order history and Z
          totals. PINs are unique - duplicates are refused. Type a new PIN
          in the box and click away to change it.
        </p>
      </section>

      <section className="panel">
        <h3>Categories</h3>
        <div className="new-product">
          <input placeholder="New category" value={catDraft}
            onChange={e => setCatDraft(e.target.value)} />
          <button className="cta small"
            onClick={() => createNamed('/api/categories', catDraft, setCatDraft)}>
            Add
          </button>
        </div>
        {catalog.map(c => (
          <div key={c.id} className="opt-row">
            <span className="arrows">
              <button className="arrow" title="Move up"
                onMouseDown={press(() => moveItem(`/api/categories/${c.id}/move`, 'up'))}>&#9650;</button>
              <button className="arrow" title="Move down"
                onMouseDown={press(() => moveItem(`/api/categories/${c.id}/move`, 'down'))}>&#9660;</button>
            </span>
            <input className="mini wide" key={`cn${c.id}-${c.name}`}
              defaultValue={c.name}
              onBlur={e => e.target.value && e.target.value !== c.name
                && renameNamed(`/api/categories/${c.id}`, e.target.value)} />
            <span className="hint small">{c.products.length} items</span>
            <button className="x big"
              onMouseDown={press(() => deleteCategory(c))}>
              &times;
            </button>
          </div>
        ))}
      </section>

      <section className="panel">
        <h3>Option groups</h3>
        <p className="hint small">
          The questions a waiter answers when adding a product. Attach a
          group to any product from the "Extra options" column in the Menu
          table below - uniform per product, nothing tied to categories.
          Untick an option to hide it from waiters without deleting it.
        </p>
        <div className="new-product">
          <input placeholder="Group name (e.g. Mixer)" value={groupDraft.name}
            onChange={e => setGroupDraft({ ...groupDraft, name: e.target.value })} />
          <select value={groupDraft.selection}
            onChange={e => setGroupDraft({ ...groupDraft, selection: e.target.value })}>
            <option value="single">pick one</option>
            <option value="multi">pick any</option>
          </select>
          <label className="check">
            <input type="checkbox" checked={groupDraft.required}
              onChange={e => setGroupDraft({ ...groupDraft, required: e.target.checked })} />
            required
          </label>
          <button className="cta small" onClick={createGroup}>Add group</button>
        </div>

        {groups.map(g => (
          <div key={g.id} className="group-row">
            <div className="group-row-head">
              <span className="arrows">
                <button className="arrow" title="Move up"
                  onMouseDown={press(() => moveItem(`/api/option-groups/${g.id}/move`, 'up'))}>&#9650;</button>
                <button className="arrow" title="Move down"
                  onMouseDown={press(() => moveItem(`/api/option-groups/${g.id}/move`, 'down'))}>&#9660;</button>
              </span>
              <input className="mini wide" key={`gn${g.id}-${g.name}`}
                defaultValue={g.name}
                onBlur={e => e.target.value && e.target.value !== g.name
                  && patchGroup(g, { name: e.target.value })} />
              <select value={g.selection}
                onChange={e => patchGroup(g, { selection: e.target.value })}>
                <option value="single">pick one</option>
                <option value="multi">pick any</option>
              </select>
              <label className="check">
                <input type="checkbox" checked={g.required}
                  onChange={e => patchGroup(g, { required: e.target.checked })} />
                required
              </label>
              <button className="ghost danger"
                onMouseDown={press(() => deleteGroup(g))}>delete</button>
            </div>

            <div className="opt-rows">
              {g.options.map(o => (
                <div key={o.id} className={o.active ? 'opt-row' : 'opt-row off'}>
                  <span className="arrows">
                    <button className="arrow" title="Move up"
                      onMouseDown={press(() => moveItem(`/api/options/${o.id}/move`, 'up'))}>&#9650;</button>
                    <button className="arrow" title="Move down"
                      onMouseDown={press(() => moveItem(`/api/options/${o.id}/move`, 'down'))}>&#9660;</button>
                  </span>
                  <label className="check" title="available to waiters">
                    <input type="checkbox" checked={o.active}
                      onChange={e => patchOption(o, { active: e.target.checked })} />
                  </label>
                  <button className={o.is_default ? 'star on' : 'star'}
                    title="default (pre-selected for the waiter)"
                    onMouseDown={press(() => patchOption(o, { is_default: !o.is_default }))}>
                    &#9733;
                  </button>
                  <input className="mini wide" key={`on${o.id}-${o.name}`}
                    defaultValue={o.name}
                    onBlur={e => e.target.value && e.target.value !== o.name
                      && patchOption(o, { name: e.target.value })} />
                  <input className="mini num" type="number" step="0.10"
                    key={`op${o.id}-${o.price_delta_cents}`}
                    defaultValue={(o.price_delta_cents / 100).toFixed(2)}
                    onBlur={e => {
                      const cents = Math.round(Number(e.target.value) * 100)
                      if (cents !== o.price_delta_cents && cents >= 0)
                        patchOption(o, { price_delta_cents: cents })
                    }} />
                  <button className="x big"
                    onMouseDown={press(() => deleteOption(g, o))}>&times;</button>
                </div>
              ))}
              <div className="opt-row">
                <span className="star ghost-slot" />
                <input className="mini wide" placeholder="new option"
                  value={optionDrafts[g.id]?.name || ''}
                  onChange={e => setOptionDrafts({ ...optionDrafts,
                    [g.id]: { ...optionDrafts[g.id], name: e.target.value } })} />
                <input className="mini num" placeholder="+€" type="number" step="0.10"
                  value={optionDrafts[g.id]?.delta || ''}
                  onChange={e => setOptionDrafts({ ...optionDrafts,
                    [g.id]: { ...optionDrafts[g.id], delta: e.target.value } })} />
                <button className="cta small" onClick={() => addOption(g)}>+</button>
              </div>
            </div>
          </div>
        ))}
      </section>

      <section className="panel">
        <h3>Menu</h3>
        <div className="new-product">
          <input placeholder="Product name" value={draft.name}
            onChange={e => setDraft({ ...draft, name: e.target.value })} />
          <input placeholder="Price €" type="number" step="0.10" value={draft.price}
            onChange={e => setDraft({ ...draft, price: e.target.value })} />
          <select value={draft.category_id}
            onChange={e => setDraft({ ...draft, category_id: e.target.value })}>
            {catalog.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button className="cta small" onClick={create}>Add</button>
        </div>
        <input className="search" placeholder="Filter menu&hellip;"
          value={menuQuery} onChange={e => setMenuQuery(e.target.value)} />
        <table>
          <thead>
            <tr><th>Product</th><th>Price</th><th>Extra options</th><th>Active</th><th></th></tr>
          </thead>
          <tbody>
            {products.filter(p => norm(p.name).includes(norm(menuQuery))).map(p => (
              <tr key={p.id} className={p.active ? '' : 'off'}>
                <td>
                  <input className="name-edit" key={`pn${p.id}-${p.name}`}
                    defaultValue={p.name}
                    onBlur={e => e.target.value && e.target.value !== p.name
                      && save(p, { name: e.target.value })} />
                </td>
                <td>
                  <input className="price-edit" type="number" step="0.10"
                    defaultValue={(p.price_cents / 100).toFixed(2)}
                    onBlur={e => {
                      const cents = Math.round(Number(e.target.value) * 100)
                      if (cents !== p.price_cents && cents >= 0) save(p, { price_cents: cents })
                    }} />
                </td>
                <td>
                  <details className="opt-picker">
                    <summary>
                      {p.option_groups.length
                        ? p.option_groups.map(g => g.name).join(', ')
                        : '—'}
                    </summary>
                    <div className="opt-picker-list">
                      {groups.map(g => (
                        <label key={g.id} className="check">
                          <input type="checkbox"
                            checked={p.option_groups.some(x => x.id === g.id)}
                            onChange={() => toggleGroupOnProduct(p, g)} />
                          {g.name}
                        </label>
                      ))}
                      {groups.length === 0 && <span className="hint small">no groups yet</span>}
                    </div>
                  </details>
                </td>
                <td>
                  <button className="ghost" onClick={() => save(p, { active: !p.active })}>
                    {p.active ? 'on' : 'off'}
                  </button>
                </td>
                <td>
                  <button className="x big"
                    onMouseDown={press(() => deleteProduct(p))}>&times;</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  )
}
