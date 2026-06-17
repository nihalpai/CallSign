"""Infrastructure state: loading, status mutation, and blast-radius semantics."""
from __future__ import annotations

from app import state


def test_loads_four_servers_all_healthy():
    servers = state.get_state()["servers"]

    assert len(servers) == 4
    assert all(s["status"] == "healthy" for s in servers)


def test_set_status_mutates_target_only():
    state.set_status("auth-01", "compromised")

    servers = {s["id"]: s["status"] for s in state.get_state()["servers"]}
    assert servers["auth-01"] == "compromised"
    assert servers["payment-gw"] == "healthy"


def test_set_status_unknown_server_is_noop():
    state.set_status("does-not-exist", "isolated")

    assert all(s["status"] == "healthy" for s in state.get_state()["servers"])


def test_set_status_all_v2_enum_values():
    for status in ("healthy", "compromised", "isolated", "degraded", "rolled_back", "recovered"):
        state._load()  # reset between iterations
        state.set_status("payment-gw", status)
        servers = {s["id"]: s["status"] for s in state.get_state()["servers"]}
        assert servers["payment-gw"] == status


def test_get_server_returns_dict():
    server = state.get_server("auth-01")

    assert server is not None
    assert server["id"] == "auth-01"


def test_get_server_unknown_returns_none():
    assert state.get_server("ghost-99") is None


def test_blast_radius_follows_dependents_transitively():
    # payment-gw and web-01 directly depend on auth-01; web-01 also via payment-gw.
    assert state.blast_radius("auth-01") == ["payment-gw", "web-01"]


def test_blast_radius_of_db_includes_downstream_auth_chain():
    # db-01 is depended on by auth-01 and payment-gw; auth-01 pulls in web-01.
    assert state.blast_radius("db-01") == ["auth-01", "payment-gw", "web-01"]


def test_blast_radius_leaf_is_empty():
    assert state.blast_radius("web-01") == []
