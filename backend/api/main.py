"""FastAPI application entrypoint.

v1 is stateless: no database, no auth, no sessions. The app exposes a health
check plus the pricing/IV/position/sensitivity/chain routes (see api/routes.py).

CORS: the allowed origins are read from the CORS_ORIGINS env var (comma
separated), never hardcoded. Locally this comes from backend/.env; in
production it is set in the Railway dashboard. The default covers local Next.js
dev plus the deployed frontend so the app is usable out of the box.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

# Load backend/.env if present (no-op in production, where Railway injects vars).
load_dotenv()

_DEFAULT_ORIGINS = "http://localhost:3000,https://option-analitycs.vercel.app"


def _allowed_origins() -> list[str]:
    """Parse CORS_ORIGINS ('a,b,c') into a clean list of origins."""
    raw = os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="Options Analytics API",
    version="0.1.0",
    summary="Pricing and risk-analysis for equity options (BSM, Greeks, IV).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    allow_credentials=False,  # stateless, no cookies/auth
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Returns a static status; no dependencies, no state."""
    return {"status": "ok"}


app.include_router(router)
