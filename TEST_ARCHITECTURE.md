<div align="center">

# 🏗️ Test Architecture

**How the test suite works under the hood**

*Lifecycle • layers • design choices • extending*

</div>

---

## 🔄 How It Works

```
pytest ──▶ conftest.py (health check) ──▶ conftest.py (creates bucket) ──▶ test runs ──▶ conftest.py (deletes bucket)
                │                                                                           │
                └──────────────────── boto3 / SigV4 / Playwright ──────────────────────────▶ RustFS (Docker)
```

> **RustFS must be running — the suite fails fast with a clear message if it isn't.**
> Each test gets a fresh bucket. No test depends on another. All cleanup is automatic.

---

## 🧱 Three Test Layers

| Layer | What it tests | How it connects | Port |
|-------|--------------|-----------------|:----:|
| **Data Plane** | S3 API (objects, buckets, uploads) | boto3 SDK | `9000` |
| **Management Plane** | Admin API (users, policies, health) | Custom SigV4 signer | `9000` |
| **UI** | Web console (login, create bucket) | Playwright + Chromium | `9001` |

Each layer has independent auth and failure modes — a bug in one doesn't block the others.

---

## ♻️ Test Lifecycle

```
1. Session-scoped health check hits /health/live
   → If RustFS is unreachable, pytest.exit() stops immediately with instructions
2. Fixture creates a unique bucket (UUID name)
3. Test runs assertions against live RustFS
4. Fixture tears down (each step runs independently):
   → Removes bucket policy
   → Deletes all objects
   → Aborts multipart uploads
   → Deletes bucket
```

Each teardown step is wrapped in `contextlib.suppress(Exception)`, so if one
step fails the remaining steps still execute. This prevents leftover buckets
when a test errors out mid-run.

---

## 📂 Key Files

| File | Does what |
|------|-----------|
| `conftest.py` | Service availability gate + fixtures + teardown helpers |
| `constants.py` | All config (env vars, timeouts, size limits — no magic numbers) |
| `sigv4.py` | AWS Signature V4 signer for admin API |
| `console_page.py` | Page Object for browser interactions |

---

## 💡 Design Choices

| Choice | Why |
|--------|-----|
| Random payloads (`os.urandom`) | Repeated bytes can hide corruption bugs |
| Session-scoped client, per-test buckets | Fast execution (one connection) with test isolation (no shared state) |
| Service availability gate | `pytest.exit()` with actionable message if RustFS is unreachable — no cryptic `ConnectionRefusedError` traces |
| Env-based config | Works locally with zero setup, overridable for future CI |
| Custom SigV4 signer | boto3 doesn't sign admin API paths — minimal standalone implementation |
| Named constants for all timeouts/limits | No magic numbers — tunable from one file (`constants.py`) |

---

## 🏃 Running

```bash
uv run pytest -m "not ui"              # API tests only (~10s)
uv run pytest                           # everything including browser
uv run pytest --log-cli-level=INFO      # see bucket lifecycle
uv run pytest --log-cli-level=DEBUG     # see all request details
```

---

## ➕ Adding a Test

1. Pick directory: `data_plane/`, `management_plane/`, or `ui/`
2. Use `created_bucket` fixture — setup/teardown is automatic
3. Use `os.urandom()` for data, not hardcoded bytes
4. Put in the right section (happy path / negative path)
5. Add a `Reference:` link in the docstring if the test verifies documented S3 behavior
6. Update counts in `README.md`

---

## 📚 S3 Specification References

Each test that verifies documented S3 behavior includes a `Reference:` link in its docstring. Key specs:

| Area | URL |
|------|-----|
| Bucket naming rules | https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html |
| Object integrity & ETags | https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html |
| Multipart uploads | https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html |
| ListObjectsV2 | https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html |
| Presigned URLs | https://docs.aws.amazon.com/AmazonS3/latest/userguide/ShareObjectPreSignedURL.html |
| Bucket policies | https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-policies.html |
| Request signing (SigV4) | https://docs.aws.amazon.com/AmazonS3/latest/userguide/signing-requests.html |
