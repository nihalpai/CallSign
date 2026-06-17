from __future__ import annotations
import json
from app.config import INFRA_STATE_PATH
from app.logging_config import get_logger

logger = get_logger(__name__)

# Module-level in-memory state — dict for mutability
_state: dict = {}


def _load() -> None:
    global _state
    try:
        with open(INFRA_STATE_PATH) as f:
            _state = json.load(f)
        logger.info("Loaded %d servers from %s", len(_state.get("servers", [])), INFRA_STATE_PATH)
    except Exception:
        logger.exception("Failed to load infrastructure state from %s", INFRA_STATE_PATH)
        _state = {"servers": []}


_load()


def get_state() -> dict:
    return _state


def get_server(server_id: str) -> dict | None:
    return _find_server(server_id)


def _find_server(server_id: str) -> dict | None:
    for s in _state["servers"]:
        if s["id"] == server_id:
            return s
    return None


def set_status(server_id: str, status: str) -> None:
    server = _find_server(server_id)
    if server is None:
        logger.warning("set_status: unknown server '%s' — ignoring", server_id)
        return
    old = server["status"]
    server["status"] = status
    logger.info("Server '%s' status: %s → %s", server_id, old, status)
    from app.events import emit_state
    emit_state()


def blast_radius(server_id: str) -> list[str]:
    """Transitive closure of servers that depend on server_id (who breaks if it
    goes down). Follows each server's `depended_on_by` edges — see
    docs/data-contracts.md §2."""
    depends = {s["id"]: s.get("depended_on_by", []) for s in _state["servers"]}
    visited: set[str] = set()
    queue = [server_id]
    while queue:
        current = queue.pop()
        for dependent in depends.get(current, []):
            if dependent not in visited:
                visited.add(dependent)
                queue.append(dependent)
    return sorted(visited)
