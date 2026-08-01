"""Shared constants for the RustFS test suite.

Values are read from environment variables with sensible defaults
for local development against a Docker-based RustFS instance.
"""

from __future__ import annotations

import os

# Endpoints — env vars allow future CI or remote target without code changes
RUSTFS_ENDPOINT: str = os.environ.get("RUSTFS_ENDPOINT", "http://localhost:9000")
RUSTFS_CONSOLE_URL: str = os.environ.get("RUSTFS_CONSOLE_URL", "http://localhost:9001")

# Credentials — defaults match docker-compose.yml root user
RUSTFS_ACCESS_KEY: str = os.environ.get("RUSTFS_ACCESS_KEY", "rustfsadmin")
RUSTFS_SECRET_KEY: str = os.environ.get("RUSTFS_SECRET_KEY", "rustfsadmin")

# AWS / S3
AWS_REGION: str = os.environ.get("AWS_REGION", "us-east-1")
AWS_SERVICE: str = "s3"

# Sizes & limits
ONE_MIB: int = 1024 * 1024
MIN_PART_SIZE: int = 5 * ONE_MIB
# Presigned URLs
PRESIGNED_URL_EXPIRY: int = 60  # seconds
PRESIGNED_URL_MIN_EXPIRY: int = 1  # seconds — shortest allowed for expiry tests
PRESIGNED_URL_EXPIRY_MARGIN: int = 2  # seconds — wait after expiry to account for clock skew

# Timeouts (seconds)
HTTP_TIMEOUT: int = 5
HTTP_TIMEOUT_LONG: int = 10
