# stoa-backend

FastAPI backend for the STOA learning platform — deployed on AWS Lambda via Mangum.

## OpenAI Build Week 2026

STOA is preparing an Education-track submission focused on the challenge-period security,
privacy, practice-integrity, and deterministic-delivery work added to the pre-existing platform.
The draft submission copy, new-work evidence, demo script, judging-access plan, and unresolved
submission blockers are collected in
[`docs/build-week-2026/`](docs/build-week-2026/README.md).

The primary challenge-period Codex session is
`019f60c5-f092-74e2-9c73-6f573e8eff1e`. Local Codex session metadata records the model as
`gpt-5.6-sol`. In that session, Codex supported authorization and privacy audits, threat-model
refinement, implementation, adversarial test design, Linux hermetic verification, and release
evidence for the submitted increment. STOA remains an AWS Bedrock-backed runtime; GPT-5.6 was
used to build and verify this increment, not represented as the production inference provider.

## Stack

- Python 3.12 · FastAPI · Mangum (Lambda adapter)
- AWS: Lambda (arm64) · API Gateway HTTP API · DynamoDB · S3 · Bedrock · Rekognition · SQS · SES
- Region: `eu-central-2` (Zurich)

## Setup

```bash
uv sync --extra dev
uv run uvicorn stoa.main:app --reload   # local dev
```

## Project Structure

```
src/stoa/
├── main.py          # FastAPI app + Mangum handler
├── config.py        # pydantic-settings
├── deps.py          # dependency injection
├── routers/         # API endpoints (auth, questions, students, teachers, parents, admin, files)
├── models/          # Pydantic request/response schemas
├── services/        # Business logic (AI, OCR, notify, report)
└── db/
    ├── dynamodb.py
    └── repositories/
```

## Environment Variables

See `src/stoa/config.py` for all settings. Copy `.env.example` → `.env` for local dev.
