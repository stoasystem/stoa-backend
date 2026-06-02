---
last_mapped_commit: 2026-06-02
---

# Stack

**Mapped:** 2026-06-02
**Scope:** Full repository

## Summary

This repository is a Python 3.12 FastAPI backend for the STOA learning platform. It is designed to run locally with Uvicorn and in production as an AWS Lambda function through Mangum.

The backend is API-only. It exposes role-specific HTTP routes for authentication, student learning, AI conversations, practice lessons, teacher/tutor escalation, parent reports, admin stats, and file upload presigning.

## Runtime

- **Language:** Python `>=3.12`, declared in `pyproject.toml`.
- **Application framework:** FastAPI, with the app created in `src/stoa/main.py`.
- **Lambda adapter:** Mangum wraps the FastAPI app as `handler` in `src/stoa/main.py`.
- **Dependency management:** `uv` project metadata in `pyproject.toml`; production lock/export materialized in `requirements.txt` and `uv.lock`.
- **Local dev command:** README recommends `uv sync --extra dev` and `uv run uvicorn stoa.main:app --reload`.

## Core Dependencies

Declared direct dependencies in `pyproject.toml`:

- `fastapi` for HTTP routing, dependency injection, request validation, and OpenAPI docs.
- `mangum` for AWS Lambda/API Gateway integration.
- `pydantic[email]` and `pydantic-settings` for request/response schemas and environment-backed settings.
- `boto3` for AWS service clients and DynamoDB access.
- `python-jose[cryptography]` for Cognito JWT validation.
- `python-multipart` for multipart compatibility, though direct S3 upload presigning is the visible upload path.
- `httpx` for fetching Cognito JWKS in `src/stoa/deps.py`.

Development dependencies in `pyproject.toml`:

- `pytest` and `pytest-asyncio`.
- `moto[dynamodb,s3,sqs,ses,rekognition]`.
- `ruff`.
- `mypy`.

## Application Entry Points

- `src/stoa/main.py` creates the FastAPI app, configures CORS, registers routers, exposes `/health`, and exports the Lambda `handler`.
- `src/stoa/config.py` defines `Settings` and the cached global `settings` instance.
- `src/stoa/deps.py` defines shared FastAPI dependencies for authentication, role checks, and AWS clients.

## Configuration

Configuration is centralized in `src/stoa/config.py` via `pydantic-settings`.

Important settings:

- `environment`, used to disable docs in production.
- `cors_origins`, defaulting to local Vite and `https://app.stoaedu.ch`.
- `aws_region`, defaulting to `eu-central-2`.
- `dynamodb_table_name`, defaulting to `stoa-main`.
- `s3_images_bucket`, `s3_reports_bucket`, and `s3_presign_expiry_seconds`.
- Cognito user pool and per-role app client IDs.
- Bedrock model ID and max token limit.
- Daily question/chat/hint limits.
- `teacher_queue_url` for SQS teacher escalation.

`.env.example` mirrors the expected environment variables for local setup.

## Deployment

Deployment is defined in `.github/workflows/deploy.yml`.

- Runs on pushes to `main`.
- Uses GitHub Actions on Ubuntu.
- Installs Python 3.12 and `uv`.
- Builds a Lambda package into `dist`.
- Installs production dependencies from `requirements.txt` targeting `manylinux2014_aarch64`.
- Copies `src/stoa` into the deployment package.
- Zips the package and updates the `stoa-api` Lambda function.
- Uses GitHub OIDC to assume `arn:aws:iam::562923011260:role/stoa-github-backend-deploy`.
- Uses AWS region `eu-central-2`.

## Tooling

- Ruff is configured with line length `100` and target Python `py312`.
- Pytest is configured with `asyncio_mode = "auto"` and `testpaths = ["tests"]`.
- Mypy is installed as a dev dependency but no repo-specific mypy configuration is present.

## Notable Stack Constraints

- The deployment package is built for Lambda ARM64; dependencies must have compatible binary wheels or pure Python distributions.
- The app assumes AWS-managed services are available at runtime; most business logic calls AWS clients directly.
- OpenAPI docs are disabled when `ENVIRONMENT=production`.
- API Gateway Lambda buffering affects `src/stoa/routers/conversations.py` streaming behavior; the SSE endpoint is pseudo-streaming.
