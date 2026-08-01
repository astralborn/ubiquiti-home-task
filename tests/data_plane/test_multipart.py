"""Multipart upload tests."""

from __future__ import annotations

import os

import pytest
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from tests.constants import MIN_PART_SIZE

# ---------------------------------------------------------------------------
# Happy path — upload and assembly
# ---------------------------------------------------------------------------


def test_multipart_complete(s3_client: S3Client, created_bucket: str) -> None:
    """Two-part upload assembles into a valid object.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html

    Steps:
        1. Initiate a multipart upload.
        2. Upload two MIN_PART_SIZE parts.
        3. Complete the upload.
        4. Verify downloaded content matches both parts.
    """
    key = "multipart.bin"
    part1 = os.urandom(MIN_PART_SIZE)
    part2 = os.urandom(MIN_PART_SIZE)

    mpu = s3_client.create_multipart_upload(Bucket=created_bucket, Key=key)
    upload_id = mpu["UploadId"]

    etag1 = s3_client.upload_part(
        Bucket=created_bucket,
        Key=key,
        UploadId=upload_id,
        PartNumber=1,
        Body=part1,
    )["ETag"]

    etag2 = s3_client.upload_part(
        Bucket=created_bucket,
        Key=key,
        UploadId=upload_id,
        PartNumber=2,
        Body=part2,
    )["ETag"]

    s3_client.complete_multipart_upload(
        Bucket=created_bucket,
        Key=key,
        UploadId=upload_id,
        MultipartUpload={
            "Parts": [
                {"PartNumber": 1, "ETag": etag1},
                {"PartNumber": 2, "ETag": etag2},
            ],
        },
    )

    data = s3_client.get_object(Bucket=created_bucket, Key=key)["Body"].read()
    expected_size = MIN_PART_SIZE * 2
    assert len(data) == expected_size, f"Expected {expected_size} bytes, got {len(data)}"
    assert data[:MIN_PART_SIZE] == part1, "Part 1 content mismatch"
    assert data[MIN_PART_SIZE:] == part2, "Part 2 content mismatch"


# ---------------------------------------------------------------------------
# Cancellation and cleanup
# ---------------------------------------------------------------------------


def test_multipart_abort(s3_client: S3Client, created_bucket: str) -> None:
    """Aborting discards all uploaded parts.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_AbortMultipartUpload.html

    Steps:
        1. Initiate a multipart upload and upload one part.
        2. Abort the upload.
        3. Verify no object was created (NoSuchKey).
    """
    key = "aborted.bin"
    mpu = s3_client.create_multipart_upload(Bucket=created_bucket, Key=key)
    upload_id = mpu["UploadId"]

    s3_client.upload_part(
        Bucket=created_bucket,
        Key=key,
        UploadId=upload_id,
        PartNumber=1,
        Body=os.urandom(MIN_PART_SIZE),
    )
    s3_client.abort_multipart_upload(
        Bucket=created_bucket,
        Key=key,
        UploadId=upload_id,
    )

    with pytest.raises(ClientError) as exc_info:
        s3_client.get_object(Bucket=created_bucket, Key=key)

    code = exc_info.value.response["Error"]["Code"]
    assert code == "NoSuchKey", f"Expected 'NoSuchKey', got '{code}'"


# ---------------------------------------------------------------------------
# Server bugs (xfail)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    reason="RustFS bug: ListMultipartUploads returns empty response",
    strict=True,
)
def test_multipart_list_in_progress(s3_client: S3Client, created_bucket: str) -> None:
    """In-progress upload appears in the listing.

    Reference:
        https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListMultipartUploads.html

    An upload remains "in progress" until complete_multipart_upload is called.
    Per the S3 spec, list_multipart_uploads must return these uploads.
    RustFS always returns an empty response (no ``Uploads`` key) regardless
    of whether parts have been uploaded — confirmed server-side bug.

    Steps:
        1. Initiate a multipart upload.
        2. Call list_multipart_uploads.
        3. Verify the upload ID appears in the listing.
    """
    key = "in-progress.bin"
    mpu = s3_client.create_multipart_upload(Bucket=created_bucket, Key=key)
    upload_id = mpu["UploadId"]

    try:
        resp = s3_client.list_multipart_uploads(Bucket=created_bucket)
        upload_ids = [u["UploadId"] for u in resp.get("Uploads", [])]
        assert upload_id in upload_ids, f"Upload {upload_id} not found in in-progress listing"
    finally:
        s3_client.abort_multipart_upload(
            Bucket=created_bucket,
            Key=key,
            UploadId=upload_id,
        )
