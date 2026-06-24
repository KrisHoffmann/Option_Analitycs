# Architecture

## Boundaries

- **Pricing math is pure.** Functions in `backend/pricing/` take numbers, return
  numbers. No network, no file I/O, no reading globals, no FastAPI imports. This is
  what makes them testable in isolation and validatable against references.
- **API routes are thin.** `backend/api/` parses requests, calls into
  `pricing/` / `strategies/` / `data/`, serializes responses. No math in routes.
- **Data access sits behind an interface.** Define one boundary —
  `get_option_chain(ticker) -> Chain` — and put the provider-specific code behind
  it. Reasoning below.

## Why isolate the data source

The plan leans on free/unofficial options data (e.g. yfinance). Be clear-eyed:
these are not contractual APIs. They break, rate-limit, change shape, and return
empty or stale chains without warning. That is acceptable for a portfolio tool —
but only if swapping the source is a one-file change, not a refactor. So:
- Everything downstream depends on *your* `Chain` type, never on the provider's
  raw shape.
- One adapter module does the provider-specific fetching and maps to `Chain`.
- The README/limitations doc states the data caveats honestly.

## Frontend <-> backend contract

- Backend owns the numerics. The frontend should **not** re-implement BSM in
  TypeScript — one source of truth. (Trivial payoff arithmetic for instant slider
  feedback can live client-side, but pricing/Greeks come from the API.)
- Define request/response types once and keep the frontend `lib/` types mirrored
  to the Python models. Sync them deliberately when they change.

## Strategy / multi-leg model

- A position is a list of legs; a leg is `{type, strike, expiry, quantity, side}`.
- Payoff-at-expiry and current-value curves are computed by summing legs over a
  spot grid.
- **Aggregate the Greeks across legs** — net delta/gamma/theta/vega/rho is the
  insight, not per-leg numbers. Build the aggregation as a first-class function,
  not an afterthought in the UI.

## State / persistence

v1 is stateless. Don't add a database, auth, or user accounts until a feature
actually requires saved state. When it does, revisit — not before.
