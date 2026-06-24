# CLAUDE.md — Options Analytics & Research Platform

A web platform for pricing, visualizing, and analyzing equity options strategies
(Black-Scholes-Merton, the Greeks, implied volatility, multi-leg payoffs). Built
as a quant-finance portfolio piece and a personal options research tool.

This file holds the **always-on** rules. Deeper guidance lives in `docs/` — read
the relevant doc before the matching work (pointers at the bottom). Keep this file
under 300 lines; push detail into the helper docs, not into here.

## Positioning — non-negotiable, affects everything

This is a **pricing and risk-analysis** tool, not a trading-signal generator.

- No P&L claims, no implied track record, no "find profitable trades" framing.
- README, UI copy, commit messages, and variable names stay on the pricing/risk
  side. If a label sounds like a recommendation ("Buy signal", "Best trade"),
  rename it ("Theoretical value", "Net delta").
- When unsure whether something crosses into signal territory, assume it does — cut it.

Why: the portfolio value comes from demonstrable quantitative rigor. A
signal-generator framing reads as naive and invites "where's the track record?" —
the wrong conversation entirely.

## Stack

- Frontend: Next.js + TypeScript. Charting per existing setup.
- Backend: Python + FastAPI. NumPy/SciPy for the numerics.
- Deploy: Vercel (frontend), Railway (backend).
- **v1 is stateless. No database until persistence earns its place.**

## Project layout (target)

```
backend/
  pricing/      # pure math: BSM, Greeks, IV solver, (later) binomial
  strategies/   # leg model, payoff + net-Greeks aggregation
  data/         # options-chain fetching, behind an interface
  api/          # FastAPI routes — thin, no math here
  tests/        # pytest; numerics tested against references
frontend/
  app/          # Next.js routes
  components/   # UI (built via the ui-ux-pro-max skill)
  lib/          # API client, shared types
docs/           # the helper docs below — also serve the human reading the repo
```

Keep pricing math **pure** — no I/O, no network, no globals. That is what makes it
testable and trustworthy. Routes and data-fetching call into it, never the reverse.

## Commands

(Fill in as the project takes shape.)
- Backend dev: `uvicorn app.main:app --reload`
- Backend tests: `pytest`
- Frontend dev: `npm run dev`
- Frontend build: `npm run build`

## Working rules

- **Modular over monolithic.** One responsibility per module. Split when a file
  starts doing two jobs — *not* at an arbitrary line count. (A forced 200-line cap
  that scatters one coherent algorithm across three files is worse than one focused
  350-line file.) Soft signal: if a file passes ~400 lines, ask whether it's doing
  too much.
- **Numerics get tested against a known reference, always.** See
  `docs/finance-standards.md`. Untested pricing code does not ship.
- **State assumptions in code and docs.** European exercise, constant vol,
  dividend handling, rate source — name them where they apply.
- Prefer editing existing files over creating new ones. Don't add scaffolding
  ("utils", "helpers", config layers) before something needs it.
- This file is a living document — update it as the codebase becomes real, and do
  not write rules here about code that doesn't exist yet.

## Frontend / UI — always use the ui-ux-pro-max skill

For **any** UI work — new components, layouts, styling, charts — invoke the
`ui-ux-pro-max` skill. No hand-rolled styling outside it.

Apply it with this project's intent in mind: the UI's job is **clarity and
trustworthiness**, not flash. This is a quant tool — dense data done legibly.
- Charts must not mislead: honest axes, labeled units, no truncated y-axes on
  payoff curves.
- Greeks and chain data read as clean tables — aligned numbers, sensible precision
  (don't show delta to 8 decimals).
- Restraint over decoration. A serious reader should trust what they see.

## Helper docs — read the relevant one before the matching work

- `docs/finance-standards.md` — **before any** pricing / Greeks / IV / numerics work.
- `docs/architecture.md` — before adding modules or changing structure.
- `docs/conventions.md` — code style, testing mechanics, commit format.
