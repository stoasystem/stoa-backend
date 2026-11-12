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

### Admin operations for agents (`stoa-admin` MCP)

`scripts/stoa_admin_mcp.py` is a local stdio MCP server that lets Claude Code, Codex and other
agents run listed admin operations on your SSO identity, without the web console's password
(#380). Add it once, from the repository root:

```bash
claude mcp add stoa-admin -- .venv/Scripts/python scripts/stoa_admin_mcp.py
```

Log in with `aws sso login --sso-session stoa`; the server uses the profile
`AdministratorAccess-562923011260` unless `STOA_ADMIN_MCP_PROFILE` or `AWS_PROFILE` names another.
Each call invokes the `stoa-api` function's `production` alias directly, which verifies the SSO
identity with STS, runs only the operations in `src/stoa/operator_calls/catalog.py`, and records
each call in the security audit stream of `operator:agent_mcp`. Tool output never carries
activation tokens or passwords.

Read-only tools: `find_accounts`, `get_account`, and (#386) `list_teacher_applications`,
`count_review_queues`, `report_email_stats`. Tools that change data take `dryRun`, and the
agent is told to rehearse with `dryRun: true` and ask you before the real run:
`invite_account`, `reissue_invitation`, `revoke_invitation` (#384). A dry run writes nothing
but its audit row; a real run mails the same activation email the console's invitation does,
and the accounts and invitations it creates name `operator:agent_mcp` as their creator.

`delete_account` (#396) is irreversible. It takes a required one-sentence `reason`, and its real
run needs `confirmAccountNumber` to repeat `accountNumber`. It deletes students and parents, and
any non-admin account still invited, through the same pipeline as an account closing itself.
It refuses active teachers, administrators, accounts with an active paid subscription and
accounts already being deleted. The scheduled deletion job finishes the work within minutes, and
`get_account` shows the deletion as in progress and then completed.

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
