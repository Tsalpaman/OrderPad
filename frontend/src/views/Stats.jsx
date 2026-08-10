import { useEffect, useState } from 'react'
import { api, euro } from '../api.js'

const HOURS_SHOWN = Array.from({ length: 18 }, (_, i) => i + 7)  // 07:00–24:00

export default function Stats() {
  const [s, setS] = useState(null)

  useEffect(() => { api('/api/stats').then(setS).catch(console.error) }, [])
  if (!s) return <main><p className="hint">Loading analytics…</p></main>

  const dayMax = Math.max(1, ...s.revenue_by_day.map(d => d.revenue_cents))
  const hourMax = Math.max(1, ...s.by_hour.map(h => h.orders))
  const shortDay = iso => iso.slice(5)  // MM-DD

  return (
    <main className="stats-page">
      <section className="stats">
        <div className="stat"><b>{s.total_orders}</b><span>orders total</span></div>
        <div className="stat"><b>{euro(s.total_revenue_cents)}</b><span>revenue total</span></div>
        <div className="stat"><b>{euro(s.avg_order_cents)}</b><span>avg order</span></div>
        <div className="stat"><b>{s.peak_hour != null ? `${s.peak_hour}:00` : '–'}</b><span>peak hour</span></div>
      </section>

      <section className="panel">
        <h3>Revenue · last 14 days</h3>
        <div className="bar-chart">
          {s.revenue_by_day.map(d => (
            <div key={d.date} className="bar-col" title={`${d.date}: ${euro(d.revenue_cents)}`}>
              <div className="bar-fill"
                style={{ height: `${Math.round(100 * d.revenue_cents / dayMax)}%` }} />
              <span className="bar-label">{shortDay(d.date)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <h3>Busiest hours <span className="hint small">· by order count</span></h3>
        <div className="bar-chart">
          {HOURS_SHOWN.map(h => {
            const row = s.by_hour[h]
            const peak = h === s.peak_hour
            return (
              <div key={h} className="bar-col"
                title={`${h}:00 — ${row.orders} orders, ${euro(row.revenue_cents)}`}>
                <div className={peak ? 'bar-fill peak' : 'bar-fill'}
                  style={{ height: `${Math.round(100 * row.orders / hourMax)}%` }} />
                <span className="bar-label">{h}</span>
              </div>
            )
          })}
        </div>
      </section>

      <section className="panel">
        <h3>Pareto · the 80/20 of the menu</h3>
        {s.total_orders === 0 ? <p className="hint">No sales yet.</p> : (
          <>
            <p className="pareto-headline">
              <b>{s.pareto_count}</b> of {s.pareto_total_products} products
              drive <b>80%</b> of revenue.
            </p>
            <table>
              <thead><tr><th>Product</th><th>Revenue</th><th>Sold</th><th>Cumulative</th></tr></thead>
              <tbody>
                {s.pareto.map((p, i) => (
                  <tr key={p.name} className={i < s.pareto_count ? 'vital-few' : ''}>
                    <td>{p.name}</td>
                    <td>{euro(p.revenue_cents)}</td>
                    <td>{p.qty}</td>
                    <td>
                      <div className="cum-cell">
                        <div className="cum-bar" style={{ width: `${p.cumulative_pct}%` }} />
                        <span>{p.cumulative_pct}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      <section className="panel">
        <h3>Sold together <span className="hint small">· product affinity</span></h3>
        {s.affinity.length === 0 ? (
          <p className="hint">Not enough multi-item orders yet to find pairings.</p>
        ) : (
          <>
            <table>
              <thead><tr><th>Pairing</th><th>Orders</th><th>Support</th><th>Lift</th></tr></thead>
              <tbody>
                {s.affinity.map(p => (
                  <tr key={`${p.a}|${p.b}`}>
                    <td>{p.a} <span className="plus">+</span> {p.b}</td>
                    <td>{p.count}</td>
                    <td>{p.support_pct}%</td>
                    <td className={p.lift >= 1.5 ? 'lift-strong' : ''}>{p.lift}×</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="hint small">
              Lift &gt; 1 means the two sell together more than chance would
              predict — candidates for a combo or a suggestive-sell prompt.
            </p>
          </>
        )}
      </section>
    </main>
  )
}
