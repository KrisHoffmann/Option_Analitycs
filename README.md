# Options Analytics & Research Platform

A web tool for **pricing and risk-analysis of equity options** — Black-Scholes-Merton
valuation, the Greeks, implied volatility, and multi-leg payoff curves. It is a
quant-finance portfolio piece and a personal options-research tool.

**Live:**
- Frontend (Vercel): https://option-analitycs.vercel.app
- Backend API (Railway)

> This is a **pricing and risk** tool, not a trading-signal generator. It tells you
> what an option is worth *under a stated model and assumptions* and how its value
> responds to the market. It makes no profit claims and gives no buy/sell advice.

---

## What it does

Three views, all driven by one Python pricing engine (the frontend never
re-implements the math):

1. **Payoff visualizer** — stack option legs (and stock) into a position and see
   the payoff-at-expiry and current model-value curves over a range of underlying
   prices, plus the position's net Greeks.
2. **Greeks visualizer** — move sliders for spot, time-to-expiry, and volatility
   and watch all five Greeks respond live, as small-multiple charts of each Greek
   against a chosen axis. Includes a BSM-vs-binomial (European/American) price
   comparison with the early-exercise premium.
3. **Chain + model-vs-market** — pull a real options chain for a liquid underlying,
   pick a contract, and put the model's price and implied volatility next to the
   market's bid/ask and quoted IV.

---

## The finance, briefly

An **option** is the right (not obligation) to buy (a **call**) or sell (a **put**)
an underlying asset at a fixed **strike** price until **expiry**. The hard question
is what that right is worth today.

The **Black-Scholes-Merton (BSM)** model answers it for European options (exercisable
only at expiry). It assumes the underlying price follows a lognormal random walk with
constant volatility, and prices the option as the discounted expected payoff under a
risk-neutral measure. The closed-form result, with Merton's continuous dividend
yield `q` (set `q = 0` for a non-dividend-paying stock):

```
Call = S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2)
Put  = K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1)
  d1 = [ln(S/K) + (r − q + σ²/2)·T] / (σ·√T)
  d2 = d1 − σ·√T
```

where `S` = spot, `K` = strike, `T` = years to expiry, `r` = risk-free rate,
`q` = continuous dividend yield, `σ` = volatility, and `N(·)` is the standard
normal CDF.

**The Greeks** are the sensitivities of the price to its inputs — the language of
options risk:

| Greek | Measures | Units in this tool |
|-------|----------|--------------------|
| Delta | ∂Price/∂Spot | per $1 of spot |
| Gamma | ∂²Price/∂Spot² | per $1 of spot, squared |
| Theta | ∂Price/∂(calendar time) | per **year** (−∂Price/∂T) |
| Vega  | ∂Price/∂Volatility | per **1.00** of vol (i.e. +100 vol points) |
| Rho   | ∂Price/∂Rate | per **1.00** of rate (i.e. +100 rate points) |

Greeks are reported as **raw partial derivatives** in the input's own units. To get
the figures more commonly quoted, divide vega and rho by 100 (per 1% move) and theta
by 365 (per calendar day). Keeping them raw is deliberate: it lets the tests validate
each Greek directly against a finite-difference of the price.

**Implied volatility (IV)** inverts the question. Given a *market price*, what
volatility `σ` makes the model reproduce it? Volatility is the one BSM input you
can't observe directly, so IV is how the market's volatility expectation is read off
option prices.

### Units

All rates and volatilities are **decimals** (`0.05` = 5%, never `5`); time is in
**years** (`0.5` = six months). This is fixed and validated at the boundaries.

---

## Assumptions (stated, because they govern every number)

- **European exercise** for the BSM engine. American exercise is priced
  separately by the binomial (CRR) model (see below).
- **Constant volatility and constant, continuously-compounded risk-free rate.**
- **Continuous dividend yield `q`** (Merton's extension), a decimal that defaults
  to `0` — a non-dividend-paying underlying. Set `q > 0` to price a
  dividend-paying name; `q` enters the `d1`/`d2` drift as `r − q` and discounts
  the spot by `e^(−qT)`. At `q = 0` every price and Greek matches the original
  BSM exactly.
- **Risk-free rate source:** a user-supplied constant (default `0.04`). There is no
  live rate feed; you set the rate you want to price against.
- **Frictionless:** no transaction costs, taxes, or borrowing constraints.

These are stated again in code, next to the functions they govern
(`backend/pricing/black_scholes.py`).

---

## The implied-volatility solver

IV has no closed form, so it is solved numerically:

> **Newton-Raphson, with a Brent (bisection) fallback.**

- **Newton-Raphson** uses the closed-form **vega** as the derivative. Because vega is
  positive everywhere the price depends on volatility, Newton usually converges in a
  handful of steps from a reasonable seed (a Brenner-Subrahmanyam ATM approximation).
- **But** vega collapses toward zero for deep in/out-of-the-money options and very
  short expiries, where Newton can stall or step out of bounds. When that happens the
  solver falls back to **Brent's method** on a bracketed volatility interval — slower,
  but guaranteed to converge given a sign change.
- **Failure is explicit.** The solver raises a clear error (never a silent `NaN` or a
  wrong number) when the market price is below intrinsic value, above the no-arbitrage
  bound, or when neither method converges. A price sitting exactly on intrinsic value
  resolves to zero volatility (no time value), rather than failing to bracket.

IV is genuinely ill-conditioned for deep-ITM/OTM contracts: when vega is tiny, the
price barely depends on volatility, so a wide band of vols reprices to nearly the same
value. The tests assert the well-posed invariant (re-pricing at the solved IV recovers
the input price) tightly, and the recovered-vol tolerance loosely for those cases —
because that is the honest precision the problem allows.

See `backend/pricing/implied_volatility.py`.

---

## The binomial (CRR) model

BSM prices European exercise only. To handle **American** options — exercisable
any time before expiry — the tool also includes a Cox-Ross-Rubinstein binomial
model (`backend/pricing/binomial.py`).

It builds a recombining tree of up/down price moves and values the option by
backward induction; at each node an American option takes the larger of holding
on (the continuation value) and exercising immediately. Default 100 steps trades
accuracy for speed (error shrinks roughly like `1/steps`, work grows like
`steps²`).

The Greeks view shows BSM next to CRR European and CRR American prices, and the
**early-exercise premium** (American − European): the extra value of being able
to exercise early. It is essentially zero for calls on non-dividend-paying stocks
(early exercise is never worthwhile) and positive for American puts — both of
which the tests check against known results.

---

## How correctness was validated

Numerics are only trustworthy if you can *demonstrate* they're right. Every pricing
output is checked against an independent reference
(`backend/tests/`, run with `pytest` — 108 tests):

- **Cited textbook value.** The BSM engine reproduces a worked example from John C.
  Hull, *Options, Futures, and Other Derivatives* (S=42, K=40, r=0.10, σ=0.20,
  T=0.5): call **4.7594** (Hull: 4.76), put **0.8086** (Hull: 0.81), delta **0.779**.
- **Put-call parity.** `C − P = S − K·e^(−rT)` is asserted across a grid of
  243 input combinations (exact to 1e-9). It catches sign, discounting, and
  rate-handling bugs in one shot.
- **Finite-difference Greeks.** Every analytical Greek is checked against a central
  finite-difference of the price (delta/vega/theta/rho by bumping the relevant input;
  gamma by differencing delta) across the same grid.
- **IV round-trip.** price → solve IV → re-price recovers the input price, including
  on deep-ITM/OTM and short-expiry stress cases.
- **Edge cases.** `T → 0` returns intrinsic value and `σ → 0` returns discounted
  intrinsic, both without dividing by zero; the guards are checked to agree with the
  analytic limit.
- **Strategy invariants.** Net Greeks equal the sum of per-leg Greeks; payoff bounds
  match known results (a vertical caps at its width, a covered call at its strike, an
  iron condor's gross payoff peaks at zero).
- **Dividends.** `q = 0` reproduces the no-dividend BSM exactly; put-call parity
  holds in its dividend form `C − P = S·e^(−qT) − K·e^(−rT)`; the Greeks still match
  finite differences with `q > 0`.
- **Binomial (CRR).** The European tree converges to BSM as steps increase
  (50/100/200, tightening tolerance); the American call on a non-dividend stock
  equals the European (zero early-exercise premium, per Merton 1973); American-put
  premiums are positive for ITM puts.

QuantLib is *not* a runtime dependency; references are textbook values and analytic
invariants.

---

## Limitations (read this part)

A model is a lens, not the truth. Where this tool is weak:

- **BSM's assumptions are known to be false in real markets.**
  - **Volatility smile/skew:** real options at different strikes trade at different
    implied vols; BSM's single constant `σ` cannot represent that. This tool prices
    each contract at a single vol and does not model the surface.
  - **Fat tails:** real returns have more extreme moves than the lognormal assumes, so
    BSM tends to misprice deep out-of-the-money options.
  - **Constant volatility and rate** are simplifications; both move in reality.
  - **Dividends** are modelled only as a single constant continuous yield `q`, not
    as the discrete, dated payments real stocks make; and **early exercise** is
    approximated by the binomial tree (with a discrete number of steps) rather than
    solved exactly.
- **Data quality and lag.** The chain comes from a free, unofficial source (yfinance).
  It can be **stale, sparse, or wrong**, rate-limit, or change shape without notice.
  When the market is closed, bid/ask often come back as `0` and the provider's quoted
  IV can be meaningless — the app falls back to the last trade and its own solved IV,
  but treat all market data as best-effort. The chain view shows the fetch timestamp
  for exactly this reason.
- **A model price is not a fair price.** It is the value *implied by BSM under the
  stated assumptions and your chosen inputs*. Disagreement with the market usually
  says more about the assumptions (or the data) than about a mispricing.

### The volatility surface specifically

The `/surface` view builds an implied-vol surface from market quotes. It is the most
data-quality-sensitive part of the tool, so its assumptions are worth stating plainly:

- **European IV fit to American prices.** Our IV solver is European BSM, but these
  underlyings list American options. We build the surface from the **OTM wing only**
  (OTM puts below spot, OTM calls above), where early-exercise premium is negligible —
  so the European-vs-American error is concentrated in the ITM contracts we *exclude*.
- **Yahoo's bid/ask can itself be delayed or stale** — it is not a real-time feed.
  This is independent of a contract's last-trade date, so a "fresh" quote can still lag
  the true market. We do not imply more data quality than the source provides.
- **`q` is a continuous-yield approximation** of the discrete, quarterly dividends real
  stocks pay (standard practice, but an approximation), sourced per ticker as a
  documented constant; the risk-free rate `r` is likewise a single documented constant.
- **We solve IV ourselves** and deliberately ignore the provider's own quoted
  `impliedVolatility` field — consistent with the backend owning all numerics.
- **The put→call crossover at the money** can leave a small cosmetic kink in the smile
  (mid-quote noise plus the European/American asymmetry); it is noted, not engineered
  away.
- **Gaps are shown, never filled.** Strikes that fail the liquidity filters or cannot
  be inverted are simply absent — no interpolation or parametric (e.g. SVI) fit, which
  could introduce arbitrage. An honest gappy surface beats a smooth fabricated one. The
  smile it reveals is itself the evidence that BSM's constant-vol assumption fails in
  practice.

---

## Architecture

```
backend/                      # Python + FastAPI; owns ALL numerics
  pricing/                    # pure math: BSM, Greeks, IV solver, sensitivity
  strategies/                 # leg model, payoff/current-value curves, net Greeks
  data/                       # options-chain interface + yfinance adapter (swappable)
  api/                        # thin FastAPI routes (parse / call / serialize)
  tests/                      # pytest; numerics validated against references
frontend/                     # Next.js + TypeScript
  app/                        # routes: / (payoff), /greeks, /chain
  components/                 # hand-rolled SVG charts + views
  lib/                        # API client, types mirrored to the Python schemas
docs/                         # finance standards, architecture, conventions
```

Design rules: pricing math is **pure** (no I/O, no globals) and is the single source
of truth; API routes contain no math; the data source sits behind one interface so
swapping it is a one-file change. The frontend never re-implements pricing.

**Stack:** Python, FastAPI, NumPy/SciPy · Next.js, TypeScript · deployed on Railway
(backend) and Vercel (frontend). v1 is **stateless** — no database, no auth.

---

## Running locally

**Backend** (Python 3.11+):

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                   # 75 tests
uvicorn api.main:app --reload            # http://localhost:8000  (/docs for the API)
```

**Frontend** (Node 18+):

```bash
cd frontend
npm install
npm run dev                              # http://localhost:3000
```

**Environment variables** (not committed):
- `backend/.env` → `CORS_ORIGINS` (comma-separated allowed origins).
- `frontend/.env.local` → `NEXT_PUBLIC_API_URL` (the backend URL; defaults to
  `http://localhost:8000`).

In production these are set in the Railway and Vercel dashboards respectively.
