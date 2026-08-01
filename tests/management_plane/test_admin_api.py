"""Admin API tests — IAM users and canned policies."""

from __future__ import annotations

import json
import uuid
from http import HTTPStatus

from tests.sigv4 import admin_request

# ---------------------------------------------------------------------------
# User management — lifecycle and verification
# ---------------------------------------------------------------------------


def test_create_and_delete_user() -> None:
    """Full user lifecycle: create -> verify -> delete.

    Steps:
        1. Create a new IAM user with a random username.
        2. Verify the user exists via user-info lookup.
        3. Confirm the user appears in list-users.
        4. Delete the user and confirm removal.
    """
    username = f"testuser-{uuid.uuid4().hex[:8]}"
    body = json.dumps({"secretKey": "TestPass123!", "status": "enabled"}).encode()

    resp = admin_request(
        "PUT",
        "/rustfs/admin/v3/add-user",
        query_params={"accessKey": username},
        body=body,
    )
    assert resp.status_code == HTTPStatus.OK, f"Create user failed: {resp.status_code} {resp.text}"

    resp = admin_request(
        "GET",
        "/rustfs/admin/v3/user-info",
        query_params={"accessKey": username},
    )
    assert resp.status_code == HTTPStatus.OK, (
        f"User info lookup failed with HTTP {resp.status_code}"
    )

    resp = admin_request("GET", "/rustfs/admin/v3/list-users")
    assert username in resp.json(), f"Created user '{username}' not found in user list"

    resp = admin_request(
        "DELETE",
        "/rustfs/admin/v3/remove-user",
        query_params={"accessKey": username},
    )
    assert resp.status_code == HTTPStatus.OK, f"Delete user failed: {resp.status_code} {resp.text}"


# ---------------------------------------------------------------------------
# Canned policies — built-in IAM policy verification
# ---------------------------------------------------------------------------


def test_list_canned_policies() -> None:
    """Built-in canned policies include the expected defaults.

    Steps:
        1. Fetch the list of canned policies.
        2. Verify known policies (readwrite, readonly, consoleAdmin) are present.
    """
    resp = admin_request("GET", "/rustfs/admin/v3/list-canned-policies")
    assert resp.status_code == HTTPStatus.OK, (
        f"List canned policies failed with HTTP {resp.status_code}"
    )
    policies = resp.json()
    assert isinstance(policies, dict), f"Expected dict, got {type(policies).__name__}"
    for name in ("readwrite", "readonly", "consoleAdmin"):
        assert name in policies, f"Expected built-in policy '{name}' not found"


def test_get_readwrite_policy() -> None:
    """The readwrite policy grants full S3 access.

    Steps:
        1. Fetch the readwrite canned policy.
        2. Verify it contains an Allow statement for s3:*.
    """
    resp = admin_request(
        "GET",
        "/rustfs/admin/v3/info-canned-policy",
        query_params={"name": "readwrite"},
    )
    assert resp.status_code == HTTPStatus.OK, (
        f"Readwrite policy lookup failed with HTTP {resp.status_code}"
    )
    data = resp.json()
    assert data["policy_name"] == "readwrite", (
        f"Expected policy_name 'readwrite', got '{data['policy_name']}'"
    )
    actions = data["policy"]["Statement"][0]["Action"]
    assert "s3:*" in actions, f"Expected 's3:*' in actions, got {actions}"
