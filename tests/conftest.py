"""Shared pytest fixtures for the RustFS test suite.

Provides reusable boto3 clients and bucket lifecycle helpers so that
individual test modules stay focused on assertions rather than setup.
"""

from __future__ import annotations

import contextlib
import logging
import uuid
from collections.abc import Generator

import boto3
import pytest
from botocore.config import Config
from mypy_boto3_s3 import S3Client
from mypy_boto3_s3.type_defs import ObjectIdentifierTypeDef

from tests.constants import (
    AWS_REGION,
    RUSTFS_ACCESS_KEY,
    RUSTFS_ENDPOINT,
    RUSTFS_SECRET_KEY,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def unique_bucket_name() -> str:
    """Generate a unique bucket name for test isolation."""
    name = f"test-bucket-{uuid.uuid4().hex[:12]}"
    logger.debug("Generated bucket name: %s", name)
    return name


def make_s3_client(
    access_key: str = RUSTFS_ACCESS_KEY,
    secret_key: str = RUSTFS_SECRET_KEY,
) -> S3Client:
    """Create a boto3 S3 client with the given credentials."""
    logger.debug("Creating S3 client for endpoint=%s, access_key=%s", RUSTFS_ENDPOINT, access_key)
    return boto3.client(
        "s3",
        endpoint_url=RUSTFS_ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=AWS_REGION,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def s3_client() -> S3Client:
    """Session-scoped boto3 S3 client for RustFS."""
    logger.info("Initializing session-scoped S3 client")
    return make_s3_client()


@pytest.fixture(scope="function")
def created_bucket(s3_client: S3Client) -> Generator[str]:
    """Create a bucket, yield its name, then tear it down completely."""
    name = unique_bucket_name()
    logger.info("Creating test bucket: %s", name)
    s3_client.create_bucket(Bucket=name)
    yield name
    logger.info("Tearing down test bucket: %s", name)
    _force_delete_bucket(s3_client, name)


# ---------------------------------------------------------------------------
# Teardown helpers (private)
# ---------------------------------------------------------------------------


def _force_delete_bucket(client: S3Client, bucket: str) -> None:
    """Best-effort removal of a bucket and all its contents."""
    for step in [
        lambda: client.delete_bucket_policy(Bucket=bucket),
        lambda: _delete_all_objects(client, bucket),
        lambda: _abort_all_multipart_uploads(client, bucket),
        lambda: client.delete_bucket(Bucket=bucket),
    ]:
        with contextlib.suppress(Exception):
            step()
    logger.debug("Bucket '%s' teardown complete", bucket)


def _delete_all_objects(client: S3Client, bucket: str) -> None:
    """Delete every object in a bucket, handling pagination."""
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        objects = page.get("Contents", [])
        if not objects:
            continue

        delete_keys: list[ObjectIdentifierTypeDef] = [{"Key": obj["Key"]} for obj in objects]
        logger.debug("Deleting %d objects from '%s'", len(delete_keys), bucket)
        client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": delete_keys},
        )


def _abort_all_multipart_uploads(client: S3Client, bucket: str) -> None:
    """Abort every in-progress multipart upload in a bucket."""
    response = client.list_multipart_uploads(Bucket=bucket)
    uploads = response.get("Uploads", [])

    if uploads:
        logger.debug("Aborting %d in-progress multipart uploads in '%s'", len(uploads), bucket)

    for upload in uploads:
        client.abort_multipart_upload(
            Bucket=bucket,
            Key=upload["Key"],
            UploadId=upload["UploadId"],
        )
