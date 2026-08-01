"""Presigned URL and authentication tests."""

from __future__ import annotations

import time
from http import HTTPStatus

import pytest
import requests
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from tests.conftest import make_s3_client
from tests.constants import (
    HTTP_TIMEOUT,
    PRESIGNED_URL_EXPIRY,
    PRESIGNED_URL_EXPIRY_MARGIN,
    PRESIGNED_URL_MIN_EXPIRY,
    RUSTFS_ACCESS_KEY,
    RUSTFS_ENDPOINT,
    RUSTFS_SECRET_KEY,
)

# ---------------------------------------------------------------------------
# Presigned URLs — unauthenticated access via signed links
# ---------------------------------------------------------------------------


def test_presigned_get(s3_client: S3Client, created_bucket: str) -> None:
    """Presigned GET URL allows unauthenticated download.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/ShareObjectPreSignedURL.html

    Steps:
        1. Upload an object.
        2. Generate a presigned GET URL.
        3. Fetch via plain HTTP (no auth) and verify content.
    """
    body = b"presigned-content"
    s3_client.put_object(Bucket=created_bucket, Key="presigned.txt", Body=body)

    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": created_bucket, "Key": "presigned.txt"},
        ExpiresIn=PRESIGNED_URL_EXPIRY,
    )

    resp = requests.get(url, timeout=HTTP_TIMEOUT)
    assert resp.status_code == HTTPStatus.OK, f"Expected 200, got {resp.status_code}"
    assert resp.content == body, f"Expected {body!r}, got {resp.content!r}"


def test_presigned_put(s3_client: S3Client, created_bucket: str) -> None:
    """Presigned PUT URL allows unauthenticated upload.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html

    Steps:
        1. Generate a presigned PUT URL.
        2. Upload via plain HTTP PUT (no auth).
        3. Download with authenticated client and verify content.
    """
    key = "uploaded-via-presign.txt"
    url = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": created_bucket, "Key": key},
        ExpiresIn=PRESIGNED_URL_EXPIRY,
    )

    body = b"uploaded-via-presigned-url"
    resp = requests.put(url, data=body, timeout=HTTP_TIMEOUT)
    assert resp.status_code == HTTPStatus.OK, f"Expected 200, got {resp.status_code}"

    downloaded = s3_client.get_object(Bucket=created_bucket, Key=key)["Body"].read()
    assert downloaded == body, f"Expected {body!r}, got {downloaded!r}"


# ---------------------------------------------------------------------------
# Auth rejection — invalid credentials must be denied
# ---------------------------------------------------------------------------


def test_wrong_access_key() -> None:
    """Non-existent access key is rejected with 403.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/signing-requests.html

    Steps:
        1. Create a client with an invalid access key.
        2. Attempt list_buckets.
        3. Verify 403 Forbidden.
    """
    client = make_s3_client(access_key="wrong-key", secret_key=RUSTFS_SECRET_KEY)
    with pytest.raises(ClientError) as exc_info:
        client.list_buckets()
    status = exc_info.value.response["ResponseMetadata"]["HTTPStatusCode"]
    assert status == HTTPStatus.FORBIDDEN, f"Wrong access key should be rejected, got {status}"


def test_wrong_secret_key() -> None:
    """Bad secret (signature mismatch) is rejected with 403.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/signing-requests.html

    Steps:
        1. Create a client with a wrong secret key.
        2. Attempt list_buckets.
        3. Verify 403 Forbidden.
    """
    client = make_s3_client(access_key=RUSTFS_ACCESS_KEY, secret_key="wrong-secret")
    with pytest.raises(ClientError) as exc_info:
        client.list_buckets()

    status = exc_info.value.response["ResponseMetadata"]["HTTPStatusCode"]
    assert status == HTTPStatus.FORBIDDEN, f"Wrong secret key should be rejected, got {status}"


def test_no_credentials() -> None:
    """Unsigned request to the S3 API returns 403.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/signing-requests.html

    Steps:
        1. Send a plain HTTP GET without any auth headers.
        2. Verify 403 Forbidden.
    """
    resp = requests.get(RUSTFS_ENDPOINT, timeout=HTTP_TIMEOUT)
    assert resp.status_code == HTTPStatus.FORBIDDEN, (
        f"Anonymous request should be rejected, got {resp.status_code}"
    )


def test_wrong_credentials_cannot_read_objects(s3_client: S3Client, created_bucket: str) -> None:
    """Attacker with wrong credentials cannot read existing objects.

    Steps:
        1. Upload a secret object with valid credentials.
        2. Attempt to read it with invalid credentials.
        3. Verify 403 Forbidden.
    """
    s3_client.put_object(Bucket=created_bucket, Key="secret.txt", Body=b"sensitive")

    bad_client = make_s3_client(access_key="attacker", secret_key="attacker-secret")
    with pytest.raises(ClientError) as exc_info:
        bad_client.get_object(Bucket=created_bucket, Key="secret.txt")

    status = exc_info.value.response["ResponseMetadata"]["HTTPStatusCode"]
    assert status == HTTPStatus.FORBIDDEN, f"Attacker should not read objects, got {status}"


def test_presigned_url_expires(s3_client: S3Client, created_bucket: str) -> None:
    """Presigned GET URL returns 403 after expiration.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/ShareObjectPreSignedURL.html

    Steps:
        1. Upload an object.
        2. Generate a presigned GET URL with minimal expiry.
        3. Confirm the URL works before expiration.
        4. Wait for expiration.
        5. Verify the same URL now returns 403 Forbidden.
    """
    key = "ephemeral.txt"
    body = b"temporary"
    s3_client.put_object(Bucket=created_bucket, Key=key, Body=body)

    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": created_bucket, "Key": key},
        ExpiresIn=PRESIGNED_URL_MIN_EXPIRY,
    )

    # Verify the URL works while still valid
    pre_resp = requests.get(url, timeout=HTTP_TIMEOUT)
    assert pre_resp.status_code == HTTPStatus.OK, (
        f"Presigned URL should work before expiry, got {pre_resp.status_code}"
    )
    assert pre_resp.content == body

    # Wait for expiration, then verify rejection
    time.sleep(PRESIGNED_URL_MIN_EXPIRY + PRESIGNED_URL_EXPIRY_MARGIN)

    post_resp = requests.get(url, timeout=HTTP_TIMEOUT)
    assert post_resp.status_code == HTTPStatus.FORBIDDEN, (
        f"Expired presigned URL should return 403, got {post_resp.status_code}"
    )
