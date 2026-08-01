"""S3 bucket lifecycle tests."""

from __future__ import annotations

from http import HTTPStatus

import pytest
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from tests.conftest import unique_bucket_name

# ---------------------------------------------------------------------------
# Happy path — create, delete, idempotency
# ---------------------------------------------------------------------------


def test_create_bucket(s3_client: S3Client) -> None:
    """New bucket appears in the global listing after creation.

    Steps:
        1. Create a bucket with a unique name.
        2. List all buckets and verify the new one is present.
    """
    name = unique_bucket_name()
    s3_client.create_bucket(Bucket=name)

    names = [b["Name"] for b in s3_client.list_buckets()["Buckets"]]
    assert name in names, f"Bucket '{name}' not found in listing"

    s3_client.delete_bucket(Bucket=name)


def test_delete_bucket(s3_client: S3Client) -> None:
    """Deleted bucket disappears from the listing.

    Steps:
        1. Create a bucket.
        2. Delete it.
        3. Verify it no longer appears in the listing.
    """
    name = unique_bucket_name()
    s3_client.create_bucket(Bucket=name)
    s3_client.delete_bucket(Bucket=name)

    names = [b["Name"] for b in s3_client.list_buckets()["Buckets"]]
    assert name not in names, (
        f"Bucket '{name}' still in listing after delete"
    )


def test_duplicate_create_is_idempotent(s3_client: S3Client, created_bucket: str) -> None:
    """Re-creating an owned bucket returns 200 and does not destroy contents.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateBucket.html

    Steps:
        1. Upload an object to the bucket.
        2. Call create_bucket again on the same bucket.
        3. Verify 200 OK.
        4. Verify the pre-existing object is still accessible.
    """
    s3_client.put_object(Bucket=created_bucket, Key="survivor.txt", Body=b"alive")

    resp = s3_client.create_bucket(Bucket=created_bucket)
    status = resp["ResponseMetadata"]["HTTPStatusCode"]
    assert status == HTTPStatus.OK, f"Expected 200, got {status}"

    data = s3_client.get_object(Bucket=created_bucket, Key="survivor.txt")["Body"].read()
    assert data == b"alive", "Re-create destroyed existing objects"


def test_bucket_isolation(s3_client: S3Client, created_bucket: str) -> None:
    """Objects in one bucket are not visible in another.

    Steps:
        1. Upload an object to the created bucket.
        2. Create a second bucket.
        3. Verify the object is not listable or GETable in the second bucket.
    """
    second_bucket = unique_bucket_name()

    s3_client.put_object(Bucket=created_bucket, Key="isolated.txt", Body=b"secret")
    s3_client.create_bucket(Bucket=second_bucket)

    try:
        objects = s3_client.list_objects_v2(Bucket=second_bucket)
        keys = [o["Key"] for o in objects.get("Contents", [])]
        assert "isolated.txt" not in keys, "Object leaked across buckets in listing"

        with pytest.raises(ClientError) as exc_info:
            s3_client.get_object(Bucket=second_bucket, Key="isolated.txt")
        code = exc_info.value.response["Error"]["Code"]
        assert code == "NoSuchKey", f"Expected 'NoSuchKey', got '{code}'"

    finally:
        s3_client.delete_bucket(Bucket=second_bucket)


# ---------------------------------------------------------------------------
# Negative path — rejection and error handling
# ---------------------------------------------------------------------------


def test_delete_non_empty_bucket_fails(s3_client: S3Client, created_bucket: str) -> None:
    """Non-empty bucket cannot be deleted (BucketNotEmpty error).

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteBucket.html

    Steps:
        1. Upload an object to the bucket.
        2. Attempt to delete the bucket.
        3. Verify BucketNotEmpty error is raised.
    """
    s3_client.put_object(Bucket=created_bucket, Key="blocker.txt", Body=b"data")

    with pytest.raises(ClientError) as exc_info:
        s3_client.delete_bucket(Bucket=created_bucket)

    code = exc_info.value.response["Error"]["Code"]
    assert code == "BucketNotEmpty", f"Expected 'BucketNotEmpty', got '{code}'"


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("AB-UPPERCASE", id="uppercase"),
        pytest.param("no_underscores", id="underscores"),
        pytest.param("ab", id="too-short"),
    ],
)
def test_invalid_bucket_name_rejected(s3_client: S3Client, name: str) -> None:
    """Bucket names violating S3 naming rules are rejected.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html

    Steps:
        1. Attempt to create a bucket with an invalid name.
        2. Verify a 400 InvalidBucketName error is returned.
    """
    with pytest.raises(ClientError) as exc_info:
        s3_client.create_bucket(Bucket=name)

    status = exc_info.value.response["ResponseMetadata"]["HTTPStatusCode"]
    assert status == HTTPStatus.BAD_REQUEST, (
        f"Expected 400 for invalid name '{name}', got {status}"
    )


def test_head_nonexistent_bucket(s3_client: S3Client) -> None:
    """HEAD on a missing bucket returns 404.

    Steps:
        1. HEAD a bucket name that does not exist.
        2. Verify 404 Not Found.
    """
    with pytest.raises(ClientError) as exc_info:
        s3_client.head_bucket(Bucket="nonexistent-bucket-xyz-999")

    status = exc_info.value.response["ResponseMetadata"]["HTTPStatusCode"]
    assert status == HTTPStatus.NOT_FOUND, f"Expected 404 for missing bucket, got {status}"
