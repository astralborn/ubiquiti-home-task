"""Bucket policy tests."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

import pytest
import requests
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client
from typeguard import typechecked

from tests.constants import HTTP_TIMEOUT, RUSTFS_ENDPOINT


@typechecked
def _public_read_policy(bucket: str) -> dict[str, Any]:
    """Build a public-read S3 bucket policy document."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicRead",
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Policy lifecycle — put, get, delete
# ---------------------------------------------------------------------------


def test_policy_round_trips(s3_client: S3Client, created_bucket: str) -> None:
    """Policy round-trips through put → get.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html

    Steps:
        1. Apply a public-read policy to the bucket.
        2. Retrieve the policy via get_bucket_policy.
        3. Verify all statement fields match (Sid, Effect, Principal, Resource).
    """
    policy = _public_read_policy(created_bucket)
    s3_client.put_bucket_policy(Bucket=created_bucket, Policy=json.dumps(policy))

    retrieved = json.loads(s3_client.get_bucket_policy(Bucket=created_bucket)["Policy"])
    stmt = retrieved["Statement"][0]
    assert stmt["Sid"] == "PublicRead", f"Expected 'PublicRead', got '{stmt['Sid']}'"
    assert stmt["Effect"] == "Allow", f"Expected 'Allow', got '{stmt['Effect']}'"
    assert stmt["Principal"] == "*", f"Expected '*', got '{stmt['Principal']}'"
    assert f"arn:aws:s3:::{created_bucket}/*" in stmt["Resource"], (
        f"Bucket ARN missing from resource: {stmt['Resource']}"
    )


def test_delete_policy(s3_client: S3Client, created_bucket: str) -> None:
    """Deleted policy is no longer retrievable.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteBucketPolicy.html

    Steps:
        1. Apply a policy to the bucket.
        2. Delete the policy.
        3. Verify get_bucket_policy raises NoSuchBucketPolicy.
    """
    policy = _public_read_policy(created_bucket)
    s3_client.put_bucket_policy(Bucket=created_bucket, Policy=json.dumps(policy))
    s3_client.delete_bucket_policy(Bucket=created_bucket)

    with pytest.raises(ClientError) as exc_info:
        s3_client.get_bucket_policy(Bucket=created_bucket)

    assert exc_info.value.response["Error"]["Code"] == "NoSuchBucketPolicy", (
        f"Unexpected error code: {exc_info.value.response['Error']['Code']}"
    )


# ---------------------------------------------------------------------------
# Access enforcement — policy actually grants/denies access
# ---------------------------------------------------------------------------


def test_public_read_allows_anonymous_access(s3_client: S3Client, created_bucket: str) -> None:
    """Anonymous GET returns correct content after public-read policy.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html

    Steps:
        1. Upload an object with known content.
        2. Apply a public-read policy to the bucket.
        3. Fetch the object anonymously (no auth headers).
        4. Verify status 200 and content matches.
    """
    s3_client.put_object(Bucket=created_bucket, Key="public.txt", Body=b"public-data")
    s3_client.put_bucket_policy(
        Bucket=created_bucket, Policy=json.dumps(_public_read_policy(created_bucket))
    )

    resp = requests.get(f"{RUSTFS_ENDPOINT}/{created_bucket}/public.txt", timeout=HTTP_TIMEOUT)
    assert resp.status_code == HTTPStatus.OK, (
        f"Expected 200 for anonymous read, got {resp.status_code}"
    )
    assert resp.content == b"public-data", (
        f"Anonymous read returned wrong content: {resp.content!r}"
    )
