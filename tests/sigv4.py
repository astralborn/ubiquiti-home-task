"""AWS SigV4 request signer for the RustFS admin API.

Why: The admin endpoints (/rustfs/admin/v3/...) require AWS Signature V4
authentication. boto3 only signs standard S3 operations, not custom admin
paths — so we need a standalone signer.

How it works:
    1. Derive a signing key from the secret (HMAC chain: secret → date → region → service).
    2. Build a canonical request (method + path + headers + payload hash).
    3. Sign it and attach the Authorization header.
    4. Send the HTTP request.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
from urllib.parse import quote, urlparse

import requests
from typeguard import typechecked

from tests.constants import (
    AWS_REGION,
    AWS_SERVICE,
    HTTP_TIMEOUT_LONG,
    RUSTFS_ACCESS_KEY,
    RUSTFS_ENDPOINT,
    RUSTFS_SECRET_KEY,
)

logger = logging.getLogger(__name__)


@typechecked
def _sign(key: bytes, msg: str) -> bytes:
    """Compute an HMAC-SHA256 digest.

    :param key: Signing key.
    :param msg: Message to sign.
    :return: Raw HMAC digest bytes.
    """
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


@typechecked
def _derive_signing_key(secret: str, date_stamp: str) -> bytes:
    """Derive the AWS SigV4 signing key for a given date.

    :param secret: AWS secret access key.
    :param date_stamp: Date in ``YYYYMMDD`` format.
    :return: Derived signing key bytes.
    """
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, AWS_REGION)
    k_service = _sign(k_region, AWS_SERVICE)
    return _sign(k_service, "aws4_request")


@typechecked
def admin_request(
    method: str,
    path: str,
    *,
    query_params: dict[str, str] | None = None,
    body: bytes = b"",
) -> requests.Response:
    """Make a SigV4-signed request to the RustFS admin API.

    :param method: HTTP method (``GET``, ``PUT``, ``DELETE``, etc.).
    :param path: Request path, e.g. ``/rustfs/admin/v3/list-users``.
    :param query_params: Optional query string key-value pairs.
    :param body: Optional request body bytes.
    :return: The HTTP response from the admin endpoint.
    """
    host = urlparse(RUSTFS_ENDPOINT).netloc
    now = datetime.datetime.now(datetime.UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    canonical_qs = (
        "&".join(
            f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in sorted(query_params.items())
        )
        if query_params
        else ""
    )

    payload_hash = hashlib.sha256(body).hexdigest()
    canonical_headers = (
        f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"

    canonical_request = (
        f"{method}\n{path}\n{canonical_qs}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    credential_scope = f"{date_stamp}/{AWS_REGION}/{AWS_SERVICE}/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )

    signing_key = _derive_signing_key(RUSTFS_SECRET_KEY, date_stamp)
    signature = hmac.new(
        signing_key,
        string_to_sign.encode(),
        hashlib.sha256,
    ).hexdigest()

    url = f"{RUSTFS_ENDPOINT}{path}"
    if canonical_qs:
        url += f"?{canonical_qs}"

    logger.info("Sending admin API %s request to %s", method, path)
    logger.debug("Admin API query string: %s", canonical_qs or "<none>")
    logger.debug("Admin API request body size: %d bytes", len(body))

    headers: dict[str, str] = {
        "Host": host,
        "X-Amz-Date": amz_date,
        "X-Amz-Content-Sha256": payload_hash,
        "Authorization": (
            f"AWS4-HMAC-SHA256 "
            f"Credential={RUSTFS_ACCESS_KEY}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        ),
    }
    if method in ("PUT", "POST") and body:
        headers["Content-Type"] = "application/json"

    response = requests.request(
        method,
        url,
        headers=headers,
        data=body,
        timeout=HTTP_TIMEOUT_LONG,
    )
    logger.info("Admin API %s %s returned HTTP %s", method, path, response.status_code)
    logger.debug("Admin API response body: %s", response.text)
    return response
