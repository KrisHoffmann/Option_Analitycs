# Finance & Numerical Standards

The credibility of this project lives or dies here. Correctness you can
*demonstrate* beats correctness you assert. Read this before touching any pricing,
Greeks, IV, or numerical code. This doc doubles as the source material for the
README's "model" and "limitations" sections.

## Every pricing output is validated against a known reference

No pricing function is "done" until it is checked against an external source:
- A textbook BSM value (cite the source in the test), or
- An established library — QuantLib is the standard reference; use it in **tests
  only**, not as a runtime dependency, or
- A known analytical edge case (e.g. a call with zero volatility equals
  `max(S − K·e^(−rT), 0)`).

Put-call parity (`C − P = S − K·e^(−rT)`, no dividends) is a free, powerful
invariant — assert it in tests across a grid of inputs. It catches sign errors,
discounting errors, and rate-handling bugs in one shot.

## Greeks: closed-form vs. finite difference

Test every analytical Greek against a finite-difference approximation of the price
function. If closed-form delta ≠ `(V(S+h) − V(S−h)) / (2h)` within tolerance, one
of them is wrong. This single check catches most Greek bugs. Do it for delta,
gamma, theta, vega, and rho — bump the relevant input, central-difference the price.

## The IV solver

This is the numerically interesting part — get it right and say how.
- **Round-trip test:** price → solve IV → re-price must recover the input price to
  tolerance.
- Choose the method deliberately. Newton-Raphson is fast but needs a good seed and
  can diverge; bisection is slower but robust. A common robust choice is Newton
  with a bisection fallback. State which you used, and why, in the README.
- **Handle non-convergence explicitly.** Return a clear failure — not a silent NaN
  or a wrong number. Deep ITM/OTM options and very short expiries are where solvers
  break; test those cases on purpose.
- Guard inputs: a market price below intrinsic value has no real IV — flag it
  rather than returning garbage.

## Numerical hygiene (edge cases that bite)

- `T → 0` (expiry): price → intrinsic; some Greeks blow up or vanish. Handle it;
  don't divide by zero.
- `σ → 0`: degenerate; price → discounted intrinsic.
- Use numerically stable formulations for `d₁`/`d₂`; watch for catastrophic
  cancellation.
- Decide and document units: are rates/vols decimals (`0.05`) or percent (`5`)?
  Pick one, validate at the boundary, never mix.

## State your assumptions — in code and in the README

Name them where they apply; don't bury them:
- European exercise (BSM). American exercise only via the binomial model, if built.
- Constant volatility and constant risk-free rate.
- Dividends: state whether ignored, or handled (e.g. continuous yield `q` in BSM).
- Risk-free rate: where does it come from? A hardcoded constant is fine for v1 —
  just say so.

## Be honest about limitations (the highest-credibility section)

The README's limitations section is the single most senior-signaling thing in the
project. Cover at least:
- BSM's known failures: the volatility smile/skew, fat-tailed returns, the
  constant-vol assumption being false in real markets.
- Data quality and lag: free/unofficial sources can be stale, sparse, or wrong;
  chains may be illiquid with wide spreads.
- Model price ≠ fair price; it is a model under stated assumptions.

Naming what the tool *can't* do is what separates this from a student exercise.
