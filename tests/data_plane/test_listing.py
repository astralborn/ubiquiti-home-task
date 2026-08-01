"""Object listing, filtering, and bulk-delete tests."""

from __future__ import annotations

import pytest
from mypy_boto3_s3 import S3Client

_LISTING_KEYS = [
    "docs/readme.md",
    "docs/guide.md",
    "images/logo.png",
    "images/banner.png",
    "root.txt",
]


@pytest.fixture()
def seeded_bucket(s3_client: S3Client, created_bucket: str) -> tuple[str, list[str]]:
    """Seed the bucket with sample objects and return (bucket, keys)."""
    for key in _LISTING_KEYS:
        s3_client.put_object(Bucket=created_bucket, Key=key, Body=b"data")

    return created_bucket, list(_LISTING_KEYS)


# ---------------------------------------------------------------------------
# Listing and filtering
# ---------------------------------------------------------------------------


def test_list_all(s3_client: S3Client, seeded_bucket: tuple[str, list[str]]) -> None:
    """All uploaded keys appear in ListObjectsV2.

    Steps:
        1. Seed the bucket with sample objects.
        2. List all objects.
        3. Verify every seeded key is present.
    """
    bucket, keys = seeded_bucket
    resp = s3_client.list_objects_v2(Bucket=bucket)
    listed = sorted(obj["Key"] for obj in resp["Contents"])
    assert listed == sorted(keys), f"Expected {sorted(keys)}, got {listed}"


def test_prefix_filter(s3_client: S3Client, seeded_bucket: tuple[str, list[str]]) -> None:
    """Prefix ``docs/`` returns only doc keys.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html

    Steps:
        1. List objects with prefix ``docs/``.
        2. Verify only docs keys are returned.
    """
    bucket, keys = seeded_bucket
    resp = s3_client.list_objects_v2(Bucket=bucket, Prefix="docs/")
    listed = [obj["Key"] for obj in resp["Contents"]]
    expected_docs = [k for k in keys if k.startswith("docs/")]
    assert len(listed) == len(expected_docs), (
        f"Expected {len(expected_docs)} docs keys, got {len(listed)}"
    )
    assert all(k.startswith("docs/") for k in listed), f"Non-docs key in results: {listed}"


def test_delimiter_produces_common_prefixes(
    s3_client: S3Client, seeded_bucket: tuple[str, list[str]]
) -> None:
    """Delimiter ``/`` groups keys into CommonPrefixes.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html

    Steps:
        1. List objects with delimiter ``/``.
        2. Verify ``docs/`` and ``images/`` appear in CommonPrefixes.
    """
    bucket, _ = seeded_bucket
    resp = s3_client.list_objects_v2(Bucket=bucket, Delimiter="/")
    prefixes = [p["Prefix"] for p in resp.get("CommonPrefixes", [])]
    assert "docs/" in prefixes, f"'docs/' missing from prefixes: {prefixes}"
    assert "images/" in prefixes, f"'images/' missing from prefixes: {prefixes}"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_pagination_with_continuation(
    s3_client: S3Client, seeded_bucket: tuple[str, list[str]]
) -> None:
    """Paginating with MaxKeys collects all keys across pages.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html

    Steps:
        1. List objects with MaxKeys=2 (forces multiple pages).
        2. Follow NextContinuationToken until IsTruncated is False.
        3. Verify all seeded keys are returned exactly once.
    """
    bucket, keys = seeded_bucket
    collected: list[str] = []
    continuation_token = None

    while True:
        kwargs: dict = {"Bucket": bucket, "MaxKeys": 2}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        resp = s3_client.list_objects_v2(**kwargs)
        collected.extend(obj["Key"] for obj in resp.get("Contents", []))

        if not resp.get("IsTruncated"):
            break
        continuation_token = resp["NextContinuationToken"]

    assert sorted(collected) == sorted(keys), (
        f"Pagination missed keys: expected {sorted(keys)}, got {sorted(collected)}"
    )


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------


def test_bulk_delete(s3_client: S3Client, created_bucket: str) -> None:
    """Multi-object delete removes all specified keys in one call.

    Steps:
        1. Upload 10 objects under the ``bulk/`` prefix.
        2. Delete all in a single delete_objects call.
        3. Verify the prefix is empty.
    """
    bulk_count = 10
    keys = [f"bulk/{i}.txt" for i in range(bulk_count)]
    for key in keys:
        s3_client.put_object(Bucket=created_bucket, Key=key, Body=b"x")

    s3_client.delete_objects(
        Bucket=created_bucket,
        Delete={"Objects": [{"Key": k} for k in keys]},
    )

    resp = s3_client.list_objects_v2(Bucket=created_bucket, Prefix="bulk/")
    assert resp.get("KeyCount", 0) == 0, "Bucket should be empty after bulk delete"
