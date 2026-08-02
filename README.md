# stoa-backend

FastAPI backend for the STOA learning platform — deployed on AWS Lambda via Mangum.

## Stack

- Python 3.12 · FastAPI · Mangum (Lambda adapter)
- AWS: Lambda (arm64) · API Gateway HTTP API · DynamoDB · S3 · Bedrock · Rekognition · SQS · SES
- Region: `eu-central-2` (Zurich)

## Setup

```bash
uv sync --extra dev
aws sso login --profile stoa
AWS_PROFILE=stoa uv run uvicorn stoa.main:app --reload   # local dev with AWS access
```

## AWS authentication

Local development and operator scripts use AWS IAM Identity Center through the `stoa` profile.
Static `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` credentials and the AWS root user are not
supported. Before live AWS work, verify the caller is account `562923011260` and an
`AWSReservedSSO_*` assumed role:

```bash
aws sso login --profile stoa
aws sts get-caller-identity --profile stoa
```

The live operator scripts default to `--profile stoa` and fail before provider access when the
caller is an IAM User, root, a non-SSO role, or the wrong AWS account.

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
