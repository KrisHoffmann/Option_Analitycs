"""FastAPI application entrypoint.

v1 is stateless: no database, no auth, no sessions. The app exposes a health
check plus the pricing/IV/position/sensitivity routes (see api/routes.py). The
chain route arrives in M5; CORS for the deployed frontend is wired in M6.
"""

from __future__ import annotations

from fastapi import FastAPI

from api.routes import router

app = FastAPI(
    title="Options Analytics API",
    version="0.1.0",
    summary="Pricing and risk-analysis for equity options (BSM, Greeks, IV).",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Returns a static status; no dependencies, no state."""
    return {"status": "ok"}


app.include_router(router)
