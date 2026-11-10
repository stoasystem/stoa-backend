"""What an agent may ask the API function to do for an operator, and nothing else (#383).

An operator call is a direct invocation of the `stoa-api` function, made with the
operator's AWS SSO credentials by the local MCP server
(`scripts/stoa_admin_mcp.py`). This module is the contract both sides read: the
event key, how the caller proves who they are, and the closed list of
operations with their arguments. It imports nothing from the application, so the
MCP server can read it without loading the API.

Every operation says whether it only reads or changes data. One that changes
data takes a `dryRun` switch and tells the agent to confirm with the person
before it runs; `tests/test_operator_calls.py` holds both rules and the list
itself, so adding an operation is a decision a reviewer sees.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# The top-level key of a direct invocation that is an operator call. API Gateway
# builds the top level of every event it sends itself, so no HTTP request can
# put this key there.
OPERATOR_CALL_KEY = "stoaOperatorCall"

# Who the audit trail names for every operator call; never a web account id.
OPERATOR_ACTOR_ID = "operator:agent_mcp"

# The caller proves who they are with a GetCallerIdentity request signed by
# their own SSO credentials, which the function sends to STS itself. Only the
# signature travels: the endpoint, the body and the content type are fixed here,
# so a signed request can only ever ask STS who signed it.
STS_BODY = "Action=GetCallerIdentity&Version=2011-06-15"
STS_CONTENT_TYPE = "application/x-www-form-urlencoded; charset=utf-8"
SIGNED_HEADERS = ("authorization", "x-amz-date", "x-amz-security-token")


def sts_endpoint(region: str) -> str:
    return f"https://sts.{region}.amazonaws.com/"


class Effect(StrEnum):
    READ = "read"
    WRITE = "write"


AccountRole = Literal["student", "parent", "teacher", "admin"]
AccountState = Literal[
    "invited",
    "pending_verification",
    "pending_review",
    "active",
    "suspended",
    "revoked",
    "archived",
    "provisioning_failed",
]


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FindAccountsArguments(_Arguments):
    query: str | None = Field(
        default=None,
        max_length=120,
        description=(
            "Part of a name, email address, account number (e.g. S26-0001) or account id."
        ),
    )
    role: AccountRole | None = None
    status: AccountState | None = None
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(
        default=None,
        max_length=2000,
        description="nextCursor from the previous page, to continue the same search.",
    )


class GetAccountArguments(_Arguments):
    userId: str | None = Field(default=None, min_length=1, max_length=128)
    accountNumber: str | None = Field(default=None, min_length=1, max_length=32)
    email: str | None = Field(default=None, min_length=3, max_length=254)

    @model_validator(mode="after")
    def _exactly_one_key(self) -> "GetAccountArguments":
        given = [value for value in (self.userId, self.accountNumber, self.email) if value]
        if len(given) != 1:
            raise ValueError("name exactly one of userId, accountNumber or email")
        return self


@dataclass(frozen=True, slots=True)
class OperationSpec:
    name: str
    effect: Effect
    title: str
    description: str
    arguments: type[BaseModel]

    def input_schema(self) -> dict[str, Any]:
        return self.arguments.model_json_schema()


OPERATIONS: tuple[OperationSpec, ...] = (
    OperationSpec(
        name="find_accounts",
        effect=Effect.READ,
        title="Find STOA accounts",
        description=(
            "Read only. Lists STOA accounts as the admin console does: account id, "
            "account number, name, email, role, account status, linked parent or "
            "student accounts, usage period end and any open invitation id. Filter by "
            "role, status and a text query matching name, email, account number or "
            "account id. Returns at most `limit` accounts; pass `nextCursor` back as "
            "`cursor` for the next page. Every call is recorded in the audit trail."
        ),
        arguments=FindAccountsArguments,
    ),
    OperationSpec(
        name="get_account",
        effect=Effect.READ,
        title="Show one STOA account",
        description=(
            "Read only. Shows one STOA account, named by exactly one of userId, "
            "accountNumber or email: the fields find_accounts lists, plus its usage "
            "period (end date, state, version) and, for a student, the effective "
            "period and who pays for it. Every call is recorded in the audit trail."
        ),
        arguments=GetAccountArguments,
    ),
)

OPERATIONS_BY_NAME: dict[str, OperationSpec] = {spec.name: spec for spec in OPERATIONS}
