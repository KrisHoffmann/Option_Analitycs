"""FastAPI application entrypoint.

v1 is stateless: no database, no auth, no sessions. For M0 the app only exposes
a health endpoint so we can confirm it boots and serves locally. Feature routes
(pricing, IV, payoff, sensitivities, chain) arrive in later milestones.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="Options Analytics API",
    version="0.1.0",
    summary="Pricing and risk-analysis for equity options (BSM, Greeks, IV).",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Returns a static status; no dependencies, no state."""
    return {"status": "ok"}
