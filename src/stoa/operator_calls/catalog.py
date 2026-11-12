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
from datetime import date
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


# What an agent may open by invitation. Administrators are not on it: opening one
# stays with the console and the bootstrap script (#380, decision 3).
InvitableRole = Literal["student", "parent", "teacher"]
# The languages an activation email is written in (`locale_service.SUPPORTED_LOCALES`).
EmailLocale = Literal["de", "en", "fr", "it"]

DRY_RUN_DESCRIPTION = (
    "true: only report what would happen; nothing is created, sent or changed. "
    "false: do it. Run with true first and show the person the answer."
)
_EXPIRY_DESCRIPTION = (
    "How long the activation link stays valid, in seconds (60 to 1209600). "
    "Default 259200 (three days)."
)
_LOCALE_DESCRIPTION = "Language of the activation email. Default de (German)."
_INVITATION_ID_DESCRIPTION = (
    "The invitation id, e.g. accountinvite_..., as get_account shows it."
)
_INVITED_ACCOUNT_NUMBER_DESCRIPTION = (
    "Account number of an invited account (e.g. S26-0001); its open invitation is used."
)


class InviteAccountArguments(_Arguments):
    role: InvitableRole
    email: str = Field(min_length=3, max_length=320)
    fullName: str = Field(default="", max_length=120)
    dateOfBirth: str | None = Field(
        default=None, max_length=32, description="YYYY-MM-DD, if known."
    )
    expirySeconds: int | None = Field(
        default=None, ge=60, le=1209600, description=_EXPIRY_DESCRIPTION
    )
    locale: EmailLocale | None = Field(default=None, description=_LOCALE_DESCRIPTION)
    dryRun: bool = Field(strict=True, description=DRY_RUN_DESCRIPTION)


class _InvitationKey(_Arguments):
    invitationId: str | None = Field(
        default=None, min_length=1, max_length=128, description=_INVITATION_ID_DESCRIPTION
    )
    accountNumber: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        description=_INVITED_ACCOUNT_NUMBER_DESCRIPTION,
    )

    @model_validator(mode="after")
    def _exactly_one_key(self) -> "_InvitationKey":
        given = [value for value in (self.invitationId, self.accountNumber) if value]
        if len(given) != 1:
            raise ValueError("name exactly one of invitationId or accountNumber")
        return self


class ReissueInvitationArguments(_InvitationKey):
    expirySeconds: int | None = Field(
        default=None, ge=60, le=1209600, description=_EXPIRY_DESCRIPTION
    )
    locale: EmailLocale | None = Field(default=None, description=_LOCALE_DESCRIPTION)
    dryRun: bool = Field(strict=True, description=DRY_RUN_DESCRIPTION)


class RevokeInvitationArguments(_InvitationKey):
    dryRun: bool = Field(strict=True, description=DRY_RUN_DESCRIPTION)


class DeleteAccountArguments(_Arguments):
    accountNumber: str = Field(
        min_length=1,
        max_length=32,
        description="Account number of the account to delete, e.g. S26-0001.",
    )
    reason: str = Field(
        min_length=1,
        max_length=300,
        description=(
            "One sentence saying why, e.g. 'Parent asked by email to close the trial "
            "account.' Kept with the deletion record and the audit trail, so name no "
            "person and no address in it."
        ),
    )
    dryRun: bool = Field(strict=True, description=DRY_RUN_DESCRIPTION)
    confirmAccountNumber: str | None = Field(
        default=None,
        max_length=32,
        description=(
            "Required when dryRun is false: the account number again, exactly as in "
            "accountNumber, typed after the person confirmed the dry run."
        ),
    )

    @model_validator(mode="after")
    def _reason_says_something(self) -> "DeleteAccountArguments":
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        return self


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


# The review states of the console's teacher application queue (#386).
TeacherApplicationReviewState = Literal["pending_review", "approved", "rejected"]


class ListTeacherApplicationsArguments(_Arguments):
    reviewState: TeacherApplicationReviewState = "pending_review"
    limit: int = Field(default=20, ge=1, le=50)


class CountReviewQueuesArguments(_Arguments):
    pass


class ReportEmailStatsArguments(_Arguments):
    weekStart: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="The Monday the weekly reports were written for, YYYY-MM-DD.",
    )


_PERIOD_ACCOUNT_DESCRIPTION = (
    "Account number of the student or parent whose usage period it is, e.g. P26-0001."
)
_EXPECTED_VERSION_DESCRIPTION = (
    "The usage period version get_usage_period or the dry run showed. Required when "
    "dryRun is false: the change is refused if the period moved since."
)
# The service's vocabulary (`usage_period.PeriodUnit`, `PeriodSource`,
# `PAYMENT_REFERENCE_MAX_LENGTH`); a test holds the two together.
PeriodUnit = Literal["months", "days"]
PeriodSource = Literal["paid", "gifted"]


class GetUsagePeriodArguments(_Arguments):
    accountNumber: str = Field(
        min_length=1, max_length=32, description=_PERIOD_ACCOUNT_DESCRIPTION
    )
    recordLimit: int = Field(
        default=10, ge=1, le=50, description="How many of the newest records to show."
    )
    cursor: str | None = Field(
        default=None,
        max_length=2048,
        description="nextCursor from the previous answer, for older records.",
    )


class ExtendUsagePeriodArguments(_Arguments):
    accountNumber: str = Field(
        min_length=1, max_length=32, description=_PERIOD_ACCOUNT_DESCRIPTION
    )
    unit: PeriodUnit = Field(description="A paid extension is counted in months.")
    amount: int = Field(ge=1, le=366)
    source: PeriodSource = Field(
        description="paid: an offline payment was received. gifted: no payment."
    )
    paymentReference: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Required when source is paid: the offline payment's reference as the "
            "bookkeeping knows it, e.g. an invoice number. No account or card numbers."
        ),
    )
    note: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional note kept on the record; name no person and no address.",
    )
    expectedVersion: int | None = Field(
        default=None, ge=0, description=_EXPECTED_VERSION_DESCRIPTION
    )
    dryRun: bool = Field(strict=True, description=DRY_RUN_DESCRIPTION)


class SetUsagePeriodArguments(_Arguments):
    accountNumber: str = Field(
        min_length=1, max_length=32, description=_PERIOD_ACCOUNT_DESCRIPTION
    )
    endsOn: date = Field(
        description="The last day the account may be used (YYYY-MM-DD, Zurich time)."
    )
    reason: str = Field(
        min_length=1,
        max_length=1000,
        description=(
            "Why the end date is put on this day, e.g. 'Corrects a month entered by "
            "mistake.' Kept on the record; name no person and no address."
        ),
    )
    expectedVersion: int | None = Field(
        default=None, ge=0, description=_EXPECTED_VERSION_DESCRIPTION
    )
    dryRun: bool = Field(strict=True, description=DRY_RUN_DESCRIPTION)


@dataclass(frozen=True, slots=True)
class OperationSpec:
    name: str
    effect: Effect
    title: str
    description: str
    arguments: type[BaseModel]
    # Takes something away that the person may still need (an invitation link, an account).
    destructive: bool = False

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
            "period (end date, state, version), for a student the effective period and "
            "who pays for it, and its deletion: none, in_progress (with the accepted "
            "time) or completed. Every call is recorded in the audit trail."
        ),
        arguments=GetAccountArguments,
    ),
    OperationSpec(
        name="invite_account",
        effect=Effect.WRITE,
        title="Invite a STOA account",
        description=(
            "Changes data. Before calling, confirm with the person: show them the role, "
            "email address and email language, run with dryRun=true first, and only "
            "call with dryRun=false once they have said yes to that answer. Opens one "
            "student, parent or teacher account in state invited and emails its "
            "single-use activation link, as the admin console's invitation does. A dry "
            "run says what would be created and sent, or why it would be refused (for "
            "example the address already holds an account of that role, named by its "
            "account number). Answers with the account number, userId, role, status "
            "and invitation id; never the activation link. Every call, dry runs "
            "included, is recorded in the audit trail."
        ),
        arguments=InviteAccountArguments,
    ),
    OperationSpec(
        name="reissue_invitation",
        effect=Effect.WRITE,
        title="Reissue a STOA invitation",
        description=(
            "Changes data. Before calling, confirm with the person: run with "
            "dryRun=true first, show them the answer, and only call with dryRun=false "
            "once they have said yes. Replaces the open invitation of an account that "
            "is still invited (named by invitationId or accountNumber): the old "
            "activation link stops working and a new one is emailed; the account and "
            "its number stay. A dry run reports the invitation's current state and "
            "whether it can be reissued. Answers with the account number, userId, "
            "role, status and the new invitation id; never the activation link. Every "
            "call, dry runs included, is recorded in the audit trail."
        ),
        arguments=ReissueInvitationArguments,
        destructive=True,
    ),
    OperationSpec(
        name="revoke_invitation",
        effect=Effect.WRITE,
        title="Revoke a STOA invitation",
        description=(
            "Changes data. Before calling, confirm with the person: run with "
            "dryRun=true first, show them the answer, and only call with dryRun=false "
            "once they have said yes. Retires an unused invitation (named by "
            "invitationId or accountNumber) so its activation link stops working; the "
            "account itself stays invited. A dry run reports the invitation's current "
            "state and whether it can be revoked. Every call, dry runs included, is "
            "recorded in the audit trail."
        ),
        arguments=RevokeInvitationArguments,
        destructive=True,
    ),
    OperationSpec(
        name="delete_account",
        effect=Effect.WRITE,
        title="Delete a STOA account",
        description=(
            "Changes data. Irreversible. Before calling, confirm with the person: run "
            "with dryRun=true first, show them the whole answer, and only call with "
            "dryRun=false, repeating the number as confirmAccountNumber, once they have "
            "said yes to deleting that account. Deletes one student or parent account "
            "in any state except archived or provisioning_failed, or a teacher account "
            "that is still invited, through the same deletion pipeline as an account "
            "closing itself: its data is erased, its parent-student links end, and its "
            "email address is released once the deletion completes. Refused for a "
            "teacher past invited, an administrator or any account holding an admin "
            "capability, an account already being "
            "deleted, and an account with an active paid subscription (settle billing "
            "first). An open invitation is revoked as part of the deletion. A dry run "
            "shows the account number, role, state, linked accounts, usage period and "
            "whether it can be deleted, or why not. The real run answers with the "
            "deletion command id, accepted time and status; get_account then shows "
            "the deletion in progress and, later, completed. Every call, dry runs "
            "included, is recorded in the audit trail with its reason."
        ),
        arguments=DeleteAccountArguments,
        destructive=True,
    ),
    OperationSpec(
        name="list_teacher_applications",
        effect=Effect.READ,
        title="List teacher applications",
        description=(
            "Read only. Lists teacher applications in one review state (pending_review, "
            "approved or rejected; default pending_review), oldest first, as the "
            "console's reviewer queue does: application id, version, status, review "
            "state, submitted time, name, subjects and verified email. Never the "
            "applicant's statement, documents or attachments. Returns at most `limit` "
            "applications; `more` says whether there are others. Every call is "
            "recorded in the audit trail."
        ),
        arguments=ListTeacherApplicationsArguments,
    ),
    OperationSpec(
        name="count_review_queues",
        effect=Effect.READ,
        title="Count STOA review queues",
        description=(
            "Read only. Counts what is waiting for an administrator: teacher "
            "applications pending review, and moderation cases open or in review. "
            "Numbers only, no cases or applications. Every call is recorded in the "
            "audit trail."
        ),
        arguments=CountReviewQueuesArguments,
    ),
    OperationSpec(
        name="report_email_stats",
        effect=Effect.READ,
        title="Weekly report email statistics",
        description=(
            "Read only. Counts the weekly parent reports of one week (weekStart, the "
            "Monday, YYYY-MM-DD) by email delivery state: sent, failed, pending, "
            "notStarted and other, as the console's report operations list shows "
            "them. Covers weekly report emails only, not invitation or verification "
            "emails. Numbers only: no address, name or error text. `complete` is "
            "false if the count stopped before reading every report. Every call is "
            "recorded in the audit trail."
        ),
        arguments=ReportEmailStatsArguments,
    ),
    OperationSpec(
        name="get_usage_period",
        effect=Effect.READ,
        title="Show a STOA usage period",
        description=(
            "Read only. Shows the usage period of one student or parent account, named "
            "by accountNumber, as the admin console does: its own end date, state "
            "(active, expired or none) and version; the students it reaches with each "
            "one's effective period and who pays for it (for a parent, every child it "
            "is currently linked to; for a student, the student); and the newest set "
            "and extension records, `recordLimit` at a time (pass `nextCursor` back as "
            "`cursor` for older ones). Every call is recorded in the audit trail."
        ),
        arguments=GetUsagePeriodArguments,
    ),
    OperationSpec(
        name="extend_usage_period",
        effect=Effect.WRITE,
        title="Extend a STOA usage period",
        description=(
            "Changes data. Before calling, confirm with the person: run with "
            "dryRun=true first, show them the end date before and after and every "
            "student it reaches, and only call with dryRun=false, passing the version "
            "the dry run showed as expectedVersion, once they have said yes. Extends a "
            "student's or parent's usage period by months or days, counted from today "
            "or the current end, whichever is later, as the admin console does. A paid "
            "extension is counted in months and names its offline payment; a gift may "
            "be days. A parent's period reaches each child it is currently linked to, "
            "unless the child's own or another parent's period ends later. A dry run "
            "answers with the period before and after and each student's effective "
            "period before and after; the real run also with the record it kept. Every "
            "call, dry runs included, is recorded in the audit trail."
        ),
        arguments=ExtendUsagePeriodArguments,
    ),
    OperationSpec(
        name="set_usage_period",
        effect=Effect.WRITE,
        title="Set a STOA usage period's end date",
        description=(
            "Changes data. Can end a period early. Before calling, confirm with the "
            "person: run with dryRun=true first, show them the end date before and "
            "after and every student it reaches (and who would lose access), and only "
            "call with dryRun=false, passing the version the dry run showed as "
            "expectedVersion, once they have said yes. Puts the end of a student's or "
            "parent's usage period on the given day, with a reason, as the admin "
            "console does: to correct a mistake or end a period early. A dry run "
            "answers with the period before and after and each student's effective "
            "period before and after; the real run also with the record it kept. Every "
            "call, dry runs included, is recorded in the audit trail."
        ),
        arguments=SetUsagePeriodArguments,
        destructive=True,
    ),
)

OPERATIONS_BY_NAME: dict[str, OperationSpec] = {spec.name: spec for spec in OPERATIONS}
