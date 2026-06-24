# Conventions

## Python (backend)

- Type hints on all public functions. Docstrings stating inputs, outputs, units,
  and assumptions for anything in `pricing/`.
- Format/lint with ruff (or black + ruff). Keep it CI-enforceable.
- Names say what they mean in finance terms: `implied_vol`, `net_delta`,
  `time_to_expiry` — not `iv2`, `d`, `t`.

## TypeScript (frontend)

- `strict` on. No `any` without a comment justifying it.
- Component and prop names describe the data, not the decoration.

## Testing

- pytest for the backend. Numerics are the priority target (see
  `docs/finance-standards.md`): reference values, put-call parity,
  finite-difference Greek checks, IV round-trips, edge cases.
- A pricing change with no accompanying test is incomplete.
- Frontend tests are lower priority for v1 — put the testing effort on the math.

## Commits

- Small, focused, present-tense ("add vega to BSM", "fix IV non-convergence on
  deep OTM").
- Keep the positioning even here: no "buy/sell signal", "profit", or P&L language
  in messages. The commit history is part of the portfolio.
- Conventional-style prefixes (feat/fix/test/docs) are fine but not required.

## Frontend work

- Reminder: all UI goes through the `ui-ux-pro-max` skill. See CLAUDE.md for the
  intent — clarity and trustworthiness, honest charts, restraint over decoration.
