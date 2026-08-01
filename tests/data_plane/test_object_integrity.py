"""Object integrity and edge-case tests."""

from __future__ import annotations

import hashlib
import os

import pytest
from mypy_boto3_s3 import S3Client

from tests.constants import ONE_MIB

# ---------------------------------------------------------------------------
# Edge cases — boundary conditions and unusual keys
# ---------------------------------------------------------------------------


def test_zero_byte_object(s3_client: S3Client, created_bucket: str) -> None:
    """Zero-byte objects can be stored and retrieved.

    Steps:
        1. Upload an empty body.
        2. GET and verify body is empty with ContentLength 0.
    """
    s3_client.put_object(Bucket=created_bucket, Key="empty.bin", Body=b"")

    resp = s3_client.get_object(Bucket=created_bucket, Key="empty.bin")
    assert resp["Body"].read() == b"", "Zero-byte object returned non-empty body"
    assert resp["ContentLength"] == 0, f"Expected ContentLength 0, got {resp['ContentLength']}"


@pytest.mark.parametrize(
    "key",
    [
        pytest.param("path/with spaces/file.txt", id="spaces"),
        pytest.param("special-chars/!@#$%^&()_+={}.txt", id="special-chars"),
        pytest.param("unicode/데이터/файл.txt", id="unicode"),
        pytest.param("a" * 200, id="long-key-200"),
        pytest.param("trailing-space/file .txt", id="trailing-space"),
        pytest.param(".hidden-top-level", id="dot-prefix"),
        pytest.param("key\twith\ttabs.bin", id="tabs"),
    ],
)
def test_special_character_keys(s3_client: S3Client, created_bucket: str, key: str) -> None:
    """Object keys with special characters round-trip correctly.

    Steps:
        1. Upload an object with a special-character key.
        2. Download it and verify content matches.
    """
    body = f"content-for-{key}".encode()
    s3_client.put_object(Bucket=created_bucket, Key=key, Body=body)

    downloaded = s3_client.get_object(Bucket=created_bucket, Key=key)["Body"].read()
    assert downloaded == body, f"Key '{key}' content mismatch"


# ---------------------------------------------------------------------------
# Data integrity — checksums and corruption detection
# ---------------------------------------------------------------------------


def test_etag_matches_md5(s3_client: S3Client, created_bucket: str) -> None:
    """ETag for single-part upload equals the MD5 hex digest (S3 contract).

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html

    Steps:
        1. Compute MD5 of a known payload.
        2. Upload it and HEAD the object.
        3. Verify ETag (stripped of quotes) matches the MD5.
    """
    body = b"etag-verification-content"
    expected_md5 = hashlib.md5(body).hexdigest()

    s3_client.put_object(Bucket=created_bucket, Key="etag.txt", Body=body)
    resp = s3_client.head_object(Bucket=created_bucket, Key="etag.txt")

    etag = resp["ETag"].strip('"')
    assert etag == expected_md5, f"ETag '{etag}' != expected MD5 '{expected_md5}'"


def test_1mib_roundtrip_integrity(s3_client: S3Client, created_bucket: str) -> None:
    """A 1 MiB single-PUT object round-trips with matching SHA-256.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html

    Verifies no data corruption for the largest single-PUT payload
    we test (below the SDK multipart threshold of ~8 MiB).

    Steps:
        1. Upload a 1 MiB payload.
        2. Download and verify size matches.
        3. Verify SHA-256 checksums match.
    """
    body = os.urandom(ONE_MIB)
    expected = hashlib.sha256(body).hexdigest()

    s3_client.put_object(Bucket=created_bucket, Key="integrity-1mib.bin", Body=body)
    downloaded = s3_client.get_object(Bucket=created_bucket,
                                      Key="integrity-1mib.bin")["Body"].read()

    assert len(downloaded) == ONE_MIB, f"Expected {ONE_MIB} bytes, got {len(downloaded)}"
    actual = hashlib.sha256(downloaded).hexdigest()
    assert actual == expected, f"SHA-256 mismatch: {expected[:16]}… vs {actual[:16]}…"
