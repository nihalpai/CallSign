"""Deployments registry — data-contracts §2b."""
from __future__ import annotations

import pytest
from app import deployments


def test_loads_deployments_on_import():
    deps = deployments.get_deployments()

    assert len(deps) >= 1


def test_payment_gw_deployment_loaded():
    dep = deployments.get_deployment("payment-gw")

    assert dep is not None
    assert dep["service"] == "payment-gw"


def test_payment_gw_current_is_unhealthy():
    dep = deployments.get_deployment("payment-gw")

    assert dep["current"]["healthy"] is False
    assert dep["current"]["deploy_id"] == "dpl_9f2"


def test_payment_gw_previous_is_healthy():
    dep = deployments.get_deployment("payment-gw")

    assert dep["previous"]["healthy"] is True
    assert dep["previous"]["deploy_id"] == "dpl_8e1"


def test_web01_deployment_loaded():
    dep = deployments.get_deployment("web-01")

    assert dep is not None
    assert dep["current"]["deploy_id"] == "dpl_w12"


def test_get_deployment_unknown_returns_none():
    assert deployments.get_deployment("ghost-99") is None


def test_current_deploy_returns_snapshot():
    snap = deployments.current_deploy("payment-gw")

    assert snap["deploy_id"] == "dpl_9f2"


def test_current_deploy_unknown_raises_key_error():
    with pytest.raises(KeyError):
        deployments.current_deploy("ghost-99")


def test_rollback_swaps_current_and_previous():
    new_current = deployments.rollback("payment-gw")

    dep = deployments.get_deployment("payment-gw")
    assert new_current["deploy_id"] == "dpl_8e1"
    assert dep["current"]["deploy_id"] == "dpl_8e1"
    assert dep["previous"]["deploy_id"] == "dpl_9f2"


def test_rollback_second_time_swaps_back():
    deployments.rollback("payment-gw")
    deployments.rollback("payment-gw")

    dep = deployments.get_deployment("payment-gw")
    assert dep["current"]["deploy_id"] == "dpl_9f2"


def test_rollback_unknown_service_returns_empty_and_logs():
    result = deployments.rollback("ghost-99")

    assert result == {}


def test_rollback_is_idempotent_across_resets(monkeypatch):
    # After conftest resets deployments via _load(), rollback should work fresh
    deployments._load()

    new_current = deployments.rollback("payment-gw")

    assert new_current["deploy_id"] == "dpl_8e1"
