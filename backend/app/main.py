from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import trigger, execute, stream, incident
from app.routes import slack as slack_route

app = FastAPI(title="CallSign AI", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.ngrok.io", "https://*.ngrok-free.app", "https://*.ngrok-free.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trigger.router)
app.include_router(execute.router)
app.include_router(stream.router)
app.include_router(incident.router)
app.include_router(slack_route.router)


@app.on_event("startup")
async def startup() -> None:
    from app.config import (
        LYZR_API_KEY,
        EXECUTION_MODE,
        AUTO_REMEDIATE,
        AUTO_REMEDIATE_MAX_SEVERITY,
        SLACK_ENABLED,
        SLACK_INTERACTIVE,
        VOICE_ENABLED,
    )
    from app.state import get_state

    servers = get_state().get("servers", [])
    print(f"[SYSTEM] CallSign AI v2 starting up")
    print(f"[SYSTEM] EXECUTION_MODE={EXECUTION_MODE}")
    print(f"[SYSTEM] AUTO_REMEDIATE={AUTO_REMEDIATE}  AUTO_REMEDIATE_MAX_SEVERITY={AUTO_REMEDIATE_MAX_SEVERITY}")
    print(f"[SYSTEM] SLACK_ENABLED={SLACK_ENABLED}  SLACK_INTERACTIVE={SLACK_INTERACTIVE}  VOICE_ENABLED={VOICE_ENABLED}")
    if not LYZR_API_KEY:
        print("[SYSTEM] LYZR_API_KEY not set — brain will use deterministic fallback")
    print(f"[SYSTEM] Loaded {len(servers)} servers from infrastructure state")
