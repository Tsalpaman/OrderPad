# Changelog

All notable changes to OrderPad, newest first. Versions were developed
iteratively against a real café/bar workflow, each one field-tested on an
Android device over the shop WiFi before moving on.

## v0.24.1
- Fixed a crash on the Statistics page: the busiest-hours chart read a
  non-existent 24:00 bucket and blanked the whole view. Now bounded to
  07:00–23:00 with a guard against any missing hour.

## v0.24
- Statistics section (admin): revenue trend, busiest-hours detection, a
  Pareto 80/20 product breakdown, and product-affinity analysis (which
  items sell together, by support and lift) - all computed from order
  history, no external service.
- Merge tables: from the order screen the waiter pulls another table's
  open orders into the current one ("Merge table here"), for parties that
  join tables. One combined bill, per-waiter Z split intact, the emptied
  table frees up instantly.
- Removed the redundant quick-add group control from the Menu (option
  groups are created in the Option groups panel above).

## v0.23
- Bar overview sorts open tabs oldest-first again, so the barman prepares
  the longest-waiting orders first. The area label on each card keeps the
  "where" visible even without geographic ordering.

## v0.22
- Fixed the last-admin guard: it still checked the retired `staff` role, so
  demoting the only admin slipped through and could lock the shop out.
- The rescue tool now auto-restores an admin when none is left — lockout is
  impossible.

## v0.21
- Login keypad accepts the full 4–8 digit PIN range (was capped at 6).
- Added `reset_pin` rescue command for recovering access from the shop PC.
- Reorder arrows on categories made visible and reliable.

## v0.20
- Human-readable error messages everywhere (no more `[object Object]`).
- Cancel a single round or void a whole open tab; paid history stays locked.
- Three roles: admin, waiter (floor only), barman (floor + live Bar screen).
- Manual up/down reordering for categories, areas, option groups and options.

## v0.19
- Fixed clipped horizontal scrollers (category tabs, product grid) on mobile.

## v0.18
- The table name moves the whole order — sent rounds and the in-progress
  cart together — to any table in any area.
- Fixed the mobile cart sheet anchoring to the top instead of the bottom.

## v0.17
- Table transfer from the waiter's open tab.

## v0.16
- Open tab shown at the table with settle; Bar becomes the admin overview.
- Mobile hardening pass.

## v0.15
- Shop mode: one server serves the whole app; phones connect over WiFi.
- Mobile bottom-sheet cart, installable home-screen icon, one-click launcher.
- Admin "Connect devices" panel.

## v0.14
- Staff management: add/rename, unique PINs, role switching, on/off.
- Option groups kept in the admin's insertion order.

## v0.13
- Product search with Greek-aware, accent-insensitive matching.
- Greek content verified end-to-end.

## v0.12
- Version endpoint and in-app version badge.

## v0.11
- Live-updating admin stats; local-time timestamps; alphabetical listing.

## v0.10
- Autonomous per-area table numbering; area labels on bar cards and receipts.

## v0.9
- Manage areas and tables in place on the Tables screen.

## v0.8
- Table areas (zones) with tabs and admin management.

## v0.7
- One open tab per table with a single Settle action; Unicode display fixes.

## v0.6
- Fixed a delete race condition; simplified option attachment to per-product.

## v0.5
- Option availability toggles, product delete, and the end-of-day Z report.

## v0.4
- Admin management of categories and tables with data-loss-guarded deletes.

## v0.3
- Fully editable options with a default choice; table transfer.

## v0.2
- Product options ("modifiers") system with admin management.

## v0.1
- Initial MVP: PIN login with roles, tables grid, order screen, live kitchen
  screen over WebSockets, admin panel, price snapshots, hand-rolled HMAC
  tokens, and a backend test suite.
