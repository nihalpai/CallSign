from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import execute, stream, approvals
from app.routes import slack as slack_route

app = FastAPI(title="CallSign AI", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.ngrok.io", "https://*.ngrok-free.app", "https://*.ngrok-free.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(approvals.router)
app.include_router(execute.router)
app.include_router(stream.router)
app.include_router(slack_route.router)


@app.on_event("startup")
async def startup() -> None:
    from app.config import (
        APPROVAL_API_KEY,
        ENRICH_REQUESTS,
        EXPERTISE_ROUTING,
        SLACK_ENABLED,
        SLACK_INTERACTIVE,
    )
    print("[SYSTEM] CallSign AI v4 starting up — human-in-the-loop approval gate")
    print(f"[SYSTEM] APPROVAL_API_KEY={'set' if APPROVAL_API_KEY else 'UNSET (auth open)'}")
    print(f"[SYSTEM] ENRICH_REQUESTS={ENRICH_REQUESTS}  EXPERTISE_ROUTING={EXPERTISE_ROUTING}")
    print(f"[SYSTEM] SLACK_ENABLED={SLACK_ENABLED}  SLACK_INTERACTIVE={SLACK_INTERACTIVE}")
