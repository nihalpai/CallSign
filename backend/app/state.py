from __future__ import annotations
import json
from app.config import INFRA_STATE_PATH

# Module-level in-memory state — dict for mutability
_state: dict = {}


def _load() -> None:
    global _state
    with open(INFRA_STATE_PATH) as f:
        _state = json.load(f)


_load()


def get_state() -> dict:
    return _state


def _find_server(server_id: str) -> dict | None:
    for s in _state["servers"]:
        if s["id"] == server_id:
            return s
    return None


def set_status(server_id: str, status: str) -> None:
    server = _find_server(server_id)
    if server is None:
        return
    server["status"] = status
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
