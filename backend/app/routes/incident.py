from __future__ import annotations
from fastapi import APIRouter, HTTPException
from app.models import Incident
from app.incidents import get_incident

router = APIRouter()


@router.get("/incident/{incident_id}", response_model=Incident)
async def get_incident_route(incident_id: str) -> dict:
    inc = get_incident(incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return inc
