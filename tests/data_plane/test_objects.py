"""Object CRUD, metadata, and copy tests."""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

# ---------------------------------------------------------------------------
# CRUD — put, get, overwrite, delete
# ---------------------------------------------------------------------------


def test_put_and_get(s3_client: S3Client, created_bucket: str) -> None:
    """Content round-trips through put → get.

    Steps:
        1. Upload an object with known content.
        2. Download it and verify content matches.
    """
    body = b"hello, rustfs!"
    s3_client.put_object(Bucket=created_bucket, Key="greeting.txt", Body=body)

    downloaded = s3_client.get_object(Bucket=created_bucket, Key="greeting.txt")["Body"].read()
    assert downloaded == body, f"Expected {body!r}, got {downloaded!r}"


def test_overwrite(s3_client: S3Client, created_bucket: str) -> None:
    """Writing to the same key replaces previous content.

    Steps:
        1. Put v1 content under a key.
        2. Put v2 content under the same key.
        3. GET returns v2.
    """
    key = "overwrite-me.txt"
    s3_client.put_object(Bucket=created_bucket, Key=key, Body=b"v1")
    s3_client.put_object(Bucket=created_bucket, Key=key, Body=b"v2")

    downloaded = s3_client.get_object(Bucket=created_bucket, Key=key)["Body"].read()
    assert downloaded == b"v2", f"Expected b'v2', got {downloaded!r}"


def test_delete(s3_client: S3Client, created_bucket: str) -> None:
    """Deleted object is no longer retrievable.

    Steps:
        1. Upload an object.
        2. Delete it.
        3. Verify GET raises NoSuchKey.
    """
    key = "to-delete.txt"
    s3_client.put_object(Bucket=created_bucket, Key=key, Body=b"bye")
    s3_client.delete_object(Bucket=created_bucket, Key=key)

    with pytest.raises(ClientError) as exc_info:
        s3_client.get_object(Bucket=created_bucket, Key=key)
    code = exc_info.value.response["Error"]["Code"]
    assert code == "NoSuchKey", f"Expected 'NoSuchKey', got '{code}'"


def test_get_nonexistent(s3_client: S3Client, created_bucket: str) -> None:
    """GET on a missing key returns NoSuchKey.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html

    Steps:
        1. Attempt to GET a key that was never created.
        2. Verify the error code is NoSuchKey.
    """
    with pytest.raises(ClientError) as exc_info:
        s3_client.get_object(Bucket=created_bucket, Key="no-such-key")

    code = exc_info.value.response["Error"]["Code"]
    assert code == "NoSuchKey", f"Expected 'NoSuchKey', got '{code}'"


def test_head_object(s3_client: S3Client, created_bucket: str) -> None:
    """HEAD returns correct size and includes an ETag.

    Steps:
        1. Upload an object with known size.
        2. HEAD the object.
        3. Verify ContentLength and ETag presence.
    """
    body = b"head-test-content"
    s3_client.put_object(Bucket=created_bucket, Key="head-test.txt", Body=body)

    resp = s3_client.head_object(Bucket=created_bucket, Key="head-test.txt")
    assert resp["ContentLength"] == len(body), (
        f"Expected ContentLength {len(body)}, got {resp['ContentLength']}"
    )
    assert "ETag" in resp, "ETag header missing from HEAD response"


# ---------------------------------------------------------------------------
# Metadata — user-defined and content-type
# ---------------------------------------------------------------------------


def test_user_metadata_preserved(s3_client: S3Client, created_bucket: str) -> None:
    """Custom user metadata survives a round-trip.

    Steps:
        1. Upload with custom metadata (author, version).
        2. HEAD the object.
        3. Verify metadata values match.
    """
    metadata = {"author": "test-suite", "version": "1"}
    s3_client.put_object(
        Bucket=created_bucket,
        Key="meta.txt",
        Body=b"content",
        Metadata=metadata,
    )

    resp = s3_client.head_object(Bucket=created_bucket, Key="meta.txt")
    for k, v in metadata.items():
        assert resp["Metadata"].get(k) == v, (
            f"Metadata '{k}' expected '{v}', got '{resp['Metadata'].get(k)}'"
        )


def test_content_type_preserved(s3_client: S3Client, created_bucket: str) -> None:
    """Content-Type is stored and returned correctly.

    Steps:
        1. Upload with explicit Content-Type application/json.
        2. HEAD the object.
        3. Verify Content-Type matches.
    """
    s3_client.put_object(
        Bucket=created_bucket,
        Key="data.json",
        Body=b'{"key": "value"}',
        ContentType="application/json",
    )

    resp = s3_client.head_object(Bucket=created_bucket, Key="data.json")
    assert resp["ContentType"] == "application/json", (
        f"Expected 'application/json', got '{resp['ContentType']}'"
    )


# ---------------------------------------------------------------------------
# Copy — within bucket, metadata preservation
# ---------------------------------------------------------------------------


def test_copy_within_same_bucket(s3_client: S3Client, created_bucket: str) -> None:
    """Copied object contains identical content.

    Steps:
        1. Upload an original object.
        2. Copy it to a new key within the same bucket.
        3. Download the copy and verify content matches.
    """
    s3_client.put_object(Bucket=created_bucket, Key="original.txt", Body=b"copy-me")
    s3_client.copy_object(
        Bucket=created_bucket,
        Key="copied.txt",
        CopySource=f"{created_bucket}/original.txt",
    )

    downloaded = s3_client.get_object(Bucket=created_bucket, Key="copied.txt")["Body"].read()
    assert downloaded == b"copy-me", f"Expected b'copy-me', got {downloaded!r}"


def test_copy_preserves_metadata(s3_client: S3Client, created_bucket: str) -> None:
    """User metadata carries over to the destination object.

    Steps:
        1. Upload with custom metadata.
        2. Copy to a new key (default COPY directive).
        3. HEAD the copy and verify metadata preserved.
    """
    s3_client.put_object(
        Bucket=created_bucket,
        Key="src.txt",
        Body=b"data",
        Metadata={"project": "rustfs-test"},
    )
    s3_client.copy_object(
        Bucket=created_bucket,
        Key="dst.txt",
        CopySource=f"{created_bucket}/src.txt",
    )

    resp = s3_client.head_object(Bucket=created_bucket, Key="dst.txt")
    assert resp["Metadata"].get("project") == "rustfs-test", (
        f"Expected metadata 'project'='rustfs-test', got {resp['Metadata']}"
    )
