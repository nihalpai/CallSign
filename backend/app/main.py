from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import trigger, execute, stream, incident

app = FastAPI(title="CallSign AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.ngrok.io", "https://*.ngrok-free.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trigger.router)
app.include_router(execute.router)
app.include_router(stream.router)
app.include_router(incident.router)


@app.on_event("startup")
async def startup() -> None:
    from app.config import LYZR_API_KEY
    from app.state import get_state
    servers = get_state().get("servers", [])
    if not LYZR_API_KEY:
        print("[SYSTEM] LYZR_API_KEY not set — brain will use fallback script")
    print(f"[SYSTEM] Loaded {len(servers)} servers from infrastructure state")
