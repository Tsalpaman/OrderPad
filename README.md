# OrderPad

A small, fully working PDA/order-management system for a cafe-bar:
waiters take orders on their phones, the bar screen updates **live over
WebSockets**, and the admin manages the menu and sees the day at a glance.

Built deliberately small: few screens, big touch targets, no feature bloat.

## Features

- **Runs on every device** - one server on the shop PC, phones and
  tablets connect over WiFi with an installable home-screen icon; on
  phones the order cart becomes a fixed bottom sheet so "Send" never
  scrolls away
- **PIN login** with roles - `staff` (Tables, Bar) and `admin` (everything)
- **Tables grid with areas** - zone tabs (Upstairs / Downstairs / Beach in
  the demo: 10/24/40 tables) with autonomous per-area numbering: every
  zone has its own "Table 1..N", and anything shown out of zone context
  (bar cards, order receipt) carries the area label. The admin manages the
  floor in place: "+ area" on the tab bar, "x" on the active tab,
  auto-numbered "+ table" and per-tile "x" inside each zone
- **Order screen** - category tabs, tap-to-add, receipt-style cart
- **Open tab at the table** - opening a table shows every round already
  sent (time, waiter, items) with a running total and a Settle button,
  so the waiter closes the table right from the phone. A wrong round is
  cancelled with one tap, or the whole open tab voided - paid history
  stays immutable so the Z report never lies. Tapping the
  table name at the top of the cart moves the WHOLE order - sent rounds
  and the in-progress cart together - to any table in any area; the Bar
  screen remains as the admin's live overview, ordered by area and table
- **Product options ("modifiers")** - tapping a product opens a bottom
  sheet with its option groups (Sugar: no sugar / medium / sweet, Ice,
  Extras with price deltas like Extra shot +0.50). Single- or multi-select,
  required groups with sensible defaults, all validated server-side.
  Free-text notes remain as a rare fallback behind a small "+ note" link
- **Option availability toggle** - untick an option (e.g. out of milk) to
  hide it from waiters instantly, without deleting it. Attachment of option
  groups to products is uniform and manual (tick per product in the Menu
  table) - deliberately not tied to categories, to keep the mental model
  simple for a small venue
- **Z report** - end-of-day totals per waiter (orders + revenue) with a
  print-ready view for closing a shift
- **Admin-managed options, fully editable** - the admin creates option
  groups and choices, edits names / price deltas / defaults inline, marks
  which option is pre-selected for the waiter (starred), and attaches
  groups to any products - no code changes, ever
- **Live bar overview (admin), one open tab per table** - every order lands
  instantly via WebSocket into its table's card, grouped as timestamped
  rounds with a running total. One **Settle** button closes the whole tab.
  Orders remain individual rows underneath, so the per-waiter Z report
  stays accurate even when two waiters serve the same table
- **Table transfer** - the table name on each tab is a dropdown: when a
  customer changes seats, the entire open tab moves and every screen
  updates instantly
- **Staff management** - the admin adds/renames staff, sets and changes
  their PINs (unique, enforced), switches between three roles - admin, waiter
  (floor only) and barman (floor + live Bar screen) -, and turns people "off"
  (blocks login, keeps their order history and Z totals). The system
  always protects the last active admin from lockout
- **Admin panel** - add products, edit names/prices inline, toggle
  availability, manage **categories** (rename inline, deletes guarded
  against data loss), today's orders / revenue / top sellers - all
  live-updating via WebSocket while the page is open. Products are listed alphabetically (with instant search); categories,
  areas, option groups and options keep the admin's own order, with
  up/down arrows to rearrange any of them at any time
- **Price & option snapshots** - order items store the price *and the
  chosen options* (name + delta) at order time, so old orders survive any
  future menu changes

## Stack

FastAPI + SQLAlchemy + SQLite (backend, zero-setup DB) - React + Vite
(frontend) - WebSockets for real-time - stateless HMAC-signed tokens
(no external JWT dependency) - pytest.

## Running it

**Shop mode - one server, every device.** Double-click
`start_orderpad.bat` (release zips ship with the frontend pre-built;
otherwise build once with `cd frontend && npm install && npm run build`).
The PC now serves the whole app: any phone or tablet on the same WiFi
opens `http://<pc-ip>:8000` - the exact address is shown in
**Admin -> Connect devices**. On the phone, browser menu ->
"Add to Home screen" gives a one-tap app icon.

**Development mode - two terminals, hot reload.**

```bash
cd backend
pip install -r requirements.txt
python -m app.seed          # demo menu, areas & tables, 3 users
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev                 # open http://localhost:5173
```

Demo PINs: staff **1111** (Maria) / **2222** (Nikos) - admin **9999**.

Tip: open two browser windows - one logged in as staff on a phone-sized
viewport, one on `/kitchen` - and watch orders land in real time.

## Locked out?

From the shop PC:

```bash
cd backend
python -m app.reset_pin 9999                    # reset the admin PIN
python -m app.reset_pin 1234 Maria             # or a specific person
python -m app.reset_pin 9999 Christos --admin  # also restore admin rights
```

If the system is ever left with no active admin, the rescued user is
promoted to admin automatically - lockout is impossible.

## Tests

```bash
cd backend && python -m pytest
```

Covers: login/PIN rejection, role guards, catalog option exposure,
required-group and single-select validation, price-delta math with
snapshots, admin option-group CRUD and product attachment, day summary.

## Design notes

- **Why SQLite:** one file, no setup, perfectly adequate for a single
  venue; swapping to Postgres is a one-line `ORDERPAD_DB` env change.
- **Why HMAC tokens instead of a JWT library:** the token is ~15 lines of
  standard-library code (sign, verify, expire) - fewer dependencies and it
  shows what a JWT actually is under the hood.
- **Why the kitchen screen trusts events but also refetches on load:**
  WebSocket messages update state incrementally; the initial GET guarantees
  correctness after a reload or reconnect.

## Roadmap

- WebSocket authentication (currently the WS channel is open in dev)
- Edit/append items on an existing open order
- Docker compose for one-command startup
- Receipt-printer integration (ESC/POS)
- i18n - Greek UI variant for real-world deployment
