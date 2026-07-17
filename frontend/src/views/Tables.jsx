import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getSession } from '../api.js'

export default function Tables() {
  const [tables, setTables] = useState([])
  const [areas, setAreas] = useState([])
  const [busyTables, setBusyTables] = useState(new Set())
  const [activeArea, setActiveArea] = useState(null)
  const navigate = useNavigate()
  const isAdmin = getSession()?.user?.role === 'admin'

  const load = () => Promise.all([
    api('/api/tables'), api('/api/orders?active=1'), api('/api/areas'),
  ])
    .then(([tableList, activeOrders, areaList]) => {
      setTables(tableList)
      setBusyTables(new Set(activeOrders.map(o => o.table.id)))
      setAreas(areaList)
      setActiveArea(prev =>
        areaList.some(a => a.id === prev) ? prev : (areaList[0]?.id ?? null))
    })
    .catch(console.error)

  useEffect(() => { load() }, [])

  const shown = tables.filter(t => t.area_id === activeArea)

  const run = async fn => {
    try { await fn(); load() } catch (e) { alert(e.message) }
  }

  const addArea = () => {
    const name = prompt('New area name:')
    if (name?.trim())
      run(() => api('/api/areas', { method: 'POST',
        body: { name: name.trim() } }))
  }

  const deleteArea = area => {
    if (confirm(`Delete area "${area.name}"?`))
      run(() => api(`/api/areas/${area.id}`, { method: 'DELETE' }))
  }

  const moveArea = (area, direction) =>
    run(() => api(`/api/areas/${area.id}/move`,
      { method: 'POST', body: { direction } }))

  const nextTableName = () => {
    const numbers = shown
      .map(t => Number((t.name.match(/(\d+)\s*$/) || [])[1]))
      .filter(n => !Number.isNaN(n))
    const next = numbers.length ? Math.max(...numbers) + 1 : shown.length + 1
    return `Table ${next}`
  }

  const addTable = () => {
    const name = prompt('Table name:', nextTableName())
    if (name?.trim())
      run(() => api('/api/tables', { method: 'POST', body: {
        name: name.trim(), area_id: activeArea,
      }}))
  }

  const deleteTable = (event, table) => {
    event.stopPropagation()
    if (confirm(`Delete ${table.name}?`))
      run(() => api(`/api/tables/${table.id}`, { method: 'DELETE' }))
  }

  return (
    <main>
      <div className="cat-tabs">
        {areas.map(a => (
          <button key={a.id} className={activeArea === a.id ? 'tab on' : 'tab'}
            onClick={() => setActiveArea(a.id)}>
            {a.name}
            {isAdmin && activeArea === a.id && (
              <>
                <span className="tab-x" title="Move left"
                  onClick={e => { e.stopPropagation(); moveArea(a, 'up') }}>
                  &#9664;
                </span>
                <span className="tab-x" title="Move right"
                  onClick={e => { e.stopPropagation(); moveArea(a, 'down') }}>
                  &#9654;
                </span>
                <span className="tab-x" title="Delete this area"
                  onClick={e => { e.stopPropagation(); deleteArea(a) }}>
                  &times;
                </span>
              </>
            )}
          </button>
        ))}
        {isAdmin && (
          <button className="tab add" onClick={addArea}>+ area</button>
        )}
      </div>

      {areas.length === 0 && (
        <p className="hint">
          {isAdmin ? 'Create an area to start adding tables.'
                   : 'No areas yet - ask the admin to set up the floor.'}
        </p>
      )}

      <div className="grid tables">
        {shown.map(t => (
          <button key={t.id}
            className={busyTables.has(t.id) ? 'tile busy' : 'tile'}
            onClick={() => navigate(`/order/${t.id}`)}>
            <span className="tile-name">{t.name}</span>
            {busyTables.has(t.id) && <span className="badge">open order</span>}
            {isAdmin && (
              <span className="tile-x" title="Delete table"
                onClick={e => deleteTable(e, t)}>&times;</span>
            )}
          </button>
        ))}
        {isAdmin && activeArea && (
          <button className="tile add" onClick={addTable}>+ table</button>
        )}
      </div>
    </main>
  )
}
