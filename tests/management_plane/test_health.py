"""Health and readiness endpoint tests."""

from __future__ import annotations

from http import HTTPStatus

import requests
from typeguard import typechecked

from tests.constants import HTTP_TIMEOUT, RUSTFS_ENDPOINT


@typechecked
def _get_health(path: str) -> dict:
    """GET a health endpoint and return the parsed JSON body."""
    resp = requests.get(f"{RUSTFS_ENDPOINT}{path}", timeout=HTTP_TIMEOUT)
    assert resp.status_code == HTTPStatus.OK, f"Expected 200, got {resp.status_code}"
    return resp.json()


# ---------------------------------------------------------------------------
# Health probes — liveness and readiness
# ---------------------------------------------------------------------------


def test_liveness() -> None:
    """Liveness probe returns a complete status payload.

    Steps:
        1. GET /health/live.
        2. Verify status, ready, service, version, and timestamp fields.
    """
    body = _get_health("/health/live")
    assert body["status"] == "ok", f"Status is '{body['status']}', expected 'ok'"
    assert body["ready"] is True, "Service reports not ready"
    assert body["service"] == "rustfs-endpoint", f"Unexpected service: {body['service']}"
    assert body.get("version"), "Version string should be present"
    assert body.get("timestamp"), "Timestamp should be present"


def test_readiness() -> None:
    """Readiness probe confirms all subsystems are connected.

    Steps:
        1. GET /health/ready.
        2. Verify top-level status is ok.
        3. Verify storage, iam, and lock subsystems report connected/ready.
    """
    body = _get_health("/health/ready")
    assert body["status"] == "ok", f"Status is '{body['status']}', expected 'ok'"
    assert body["ready"] is True, "Service reports not ready"

    details = body["details"]
    for subsystem in ("storage", "iam", "lock"):
        assert details[subsystem]["status"] == "connected", (
            f"Subsystem '{subsystem}' is not connected"
        )
        assert details[subsystem]["ready"] is True, f"Subsystem '{subsystem}' is not ready"
