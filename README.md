# stoa-backend

FastAPI backend for the STOA learning platform — deployed on AWS Lambda via Mangum.

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
