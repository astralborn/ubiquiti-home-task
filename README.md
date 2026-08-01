<div align="center">

# 🧪 RustFS Test Suite

**Automated QA for S3-compatible object storage**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![pytest](https://img.shields.io/badge/framework-pytest-orange.svg)](https://pytest.org/)

*Test suite covering data plane • management plane • browser UI*

</div>

---

## ⚡ Quick Start

> **Requires:** Docker • Python 3.12+ • [uv](https://docs.astral.sh/uv/) (Python package manager)
>
> `uv` manages dependencies and auto-downloads the right Python version if needed — no manual Python install required.

```bash
# 1. Start RustFS
docker compose -f task_assets/docker-compose.yml up -d

# 2. Install dependencies
uv sync

# 3. Run tests (~10 seconds)
uv run pytest -m "not ui"
```

### 🌐 Browser UI test (optional)

The UI test drives real Chromium via Playwright:

```bash
uv run playwright install chromium   # one-time, ~200 MB
uv run pytest                        # full suite including UI
```

<details>
<summary>📋 <b>More run options</b></summary>

```bash
uv run pytest tests/data_plane/      # one layer at a time
uv run pytest -k multipart           # one topic at a time
uv run pytest -v                     # verbose — see every test name
```

Every run generates an **HTML report** at `reports/report.html`.
</details>

### ⚙️ Configuration

All settings read from environment variables with defaults for local Docker:

| Variable | Default | Description |
|----------|---------|-------------|
| `RUSTFS_ENDPOINT` | `http://localhost:9000` | S3 API endpoint |
| `RUSTFS_CONSOLE_URL` | `http://localhost:9001` | Web console URL |
| `RUSTFS_ACCESS_KEY` | `rustfsadmin` | Root access key |
| `RUSTFS_SECRET_KEY` | `rustfsadmin` | Root secret key |
| `AWS_REGION` | `us-east-1` | Region for SigV4 signing |

---

## 📊 What's Tested

> **52 tests** | **50 passing** | **1 xfail (server bug)** | **1 browser UI**

### Data Plane — 43 tests

Exercises the S3 API on port 9000 via boto3.

| Module | Tests | Focus |
|--------|:-----:|-------|
| `test_objects.py` | 9 | CRUD, overwrite, delete, HEAD, metadata, content-type, copy |
| `test_object_integrity.py` | 10 | Zero-byte, special-char keys, SHA-256, ETag/MD5, 1 MiB transfer |
| `test_buckets.py` | 9 | Create/delete, non-empty guard, idempotent, isolation, invalid names, 404 |
| `test_listing.py` | 5 | ListObjectsV2, prefix, delimiter, pagination, bulk delete |
| `test_multipart.py` | 3 | Complete upload, abort, list in-progress *(xfail)* |
| `test_presigned.py` | 7 | Presigned GET/PUT, auth rejection, cross-user isolation, URL expiry |

### Management Plane — 8 tests

Exercises admin API (SigV4-signed) and health probes.

| Module | Tests | Focus |
|--------|:-----:|-------|
| `test_admin_api.py` | 3 | IAM lifecycle, canned policies, policy content |
| `test_bucket_policy.py` | 3 | Policy round-trip, delete, anonymous access |
| `test_health.py` | 2 | Liveness (5 fields), readiness (3 subsystems) |

### Browser UI — 1 test

| Module | Focus |
|--------|-------|
| `test_browser.py` | Login → create bucket → verify it appears (Playwright + Page Object) |

---

## 🎯 Approach

Tests prioritized by impact — what breaks the service the most:

| Priority | Area | Why |
|:--------:|------|-----|
| 🔴 1 | Data integrity | Corrupted data = service is useless |
| 🟠 2 | Security | Auth bypass = anyone can read your files |
| 🟡 3 | Core CRUD | Basic ops fail = nothing else works |
| 🟢 4 | Health probes | Wrong response = bad routing in production |

> Most assertions check response content and behavior, not just status codes. Status codes are validated where they *are* the contract (e.g., 403 on auth rejection).

---

## 🐛 Discovered Issues

**`ListMultipartUploads` returns empty — `test_multipart_list_in_progress`**

When a multipart upload is initiated but not yet completed, the S3 API should let you
list those in-progress uploads. RustFS returns an empty response instead — the uploads
exist but are invisible.

**Why it matters:** Without this, cleanup tools can't find and remove stale uploads
that were never completed (e.g., after a network failure). Those orphaned parts keep
consuming storage with no way to discover them through the API.

**How I confirmed it's a server bug:**
- Initiated a multipart upload (no parts sent) → listed → empty
- Per the [S3 specification](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListMultipartUploads.html), an upload is "in-progress" immediately after `CreateMultipartUpload` and must appear in the listing

Marked as `xfail` so the test documents the bug without blocking the suite.

---

## 📁 Project Structure

```
tests/
├── conftest.py                    # Service gate, fixtures, teardown
├── constants.py                   # Endpoints, credentials, timeouts, size limits
├── sigv4.py                       # AWS SigV4 signer for admin API
│
├── data_plane/
│   ├── test_objects.py            # Object CRUD, metadata, copy
│   ├── test_object_integrity.py   # Checksums, edge cases, single-PUT size limits
│   ├── test_buckets.py            # Bucket lifecycle
│   ├── test_listing.py            # Listing, filtering, bulk delete
│   ├── test_multipart.py          # Multipart uploads
│   └── test_presigned.py          # Presigned URLs, auth + expiry
│
├── management_plane/
│   ├── test_admin_api.py          # IAM management
│   ├── test_bucket_policy.py      # Bucket policies
│   └── test_health.py             # Health probes
│
└── ui/
    ├── console_page.py            # Page Object pattern
    └── test_browser.py            # Playwright browser test
```

---

## 📌 Assumptions

| # | Assumption |
|:-:|------------|
| 1 | RustFS is running before tests start — the suite checks `/health/live` and fails fast with instructions if not |
| 2 | Default credentials (`rustfsadmin`/`rustfsadmin`) unless overridden via env vars |
| 3 | Ports 9000 (S3 API) and 9001 (console) are available |
| 4 | Single-node deployment — no cluster or replication testing |

## ⚠️ Limitations

| Area | Gap | Impact |
|------|-----|--------|
| Concurrency | Sequential execution only | Race conditions not covered |
| Resilience | Healthy localhost assumed | Service availability is checked at startup; no timeout/retry/network-failure testing |
| Multi-tenant | Root account + rejection tests only | Two *valid* users never interact |
| Scope | Functional only | No load/stress/performance testing |

---

## 🔮 What I Would Test Next

| Priority | Area | What | Why |
|:--------:|------|------|-----|
| 🔴 | Multi-tenant | Two IAM users, verify bucket isolation between them | Only root tested today |
| 🔴 | Concurrency | Parallel writes to same key | Corruption under load |
| 🔴 | Range reads | Partial GET with `Range` header, verify correct byte slice | Common S3 feature, untested |
| 🟡 | E2E flows | UI action → verify via API | Proves full stack together |
| 🟡 | Resilience | Slow connections, drops mid-upload | Real networks ≠ localhost |
| 🟡 | CI pipeline | Auto-start RustFS, run on push | Tests only help if they run |
| 🟢 | Versioning | Upload multiple versions, retrieve specific | Common S3 feature |
| 🟢 | Load testing | Throughput under sustained pressure | Performance baseline |

---

## 📚 S3 Specification References

Tests validate behavior against the official AWS S3 documentation:

| Area | Reference |
|------|-----------|
| Bucket naming rules | https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html |
| Object integrity & ETags | https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html |
| Multipart uploads | https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html |
| ListObjectsV2 (prefix, delimiter, pagination) | https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html |
| Presigned URLs | https://docs.aws.amazon.com/AmazonS3/latest/userguide/ShareObjectPreSignedURL.html |
| Bucket policies | https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html |
| Request signing (SigV4) | https://docs.aws.amazon.com/AmazonS3/latest/userguide/signing-requests.html |
| CreateBucket (idempotency) | https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateBucket.html |
| DeleteBucket (non-empty guard) | https://docs.aws.amazon.com/AmazonS3/latest/API/API_DeleteBucket.html |
| GetObject (NoSuchKey) | https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html |
| ListMultipartUploads | https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListMultipartUploads.html |

