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
_LOCALE_DESCRIPTION = (
    "Language of the activation email. Leave it out when the invitee's language is not "
    "known: the email then says everything in German, French, Italian and English."
)
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


# -- curriculum (#426) ---------------------------------------------------------------

# The largest migration manifest one call carries, as compact JSON. A direct
# invocation takes at most 6 MB of payload; this leaves room for the rest of the
# call. The knowledge-base manifests run to a few hundred KB.
MAX_MANIFEST_BYTES = 4_000_000
# How many lessons one publish call moves. The run stops between lessons when it
# reaches this, and a new dry run and call go on from there.
MAX_PUBLISH_LESSONS = 60

_LESSON_ID_DESCRIPTION = "The lesson's publicLessonId, e.g. zap1-brueche-addieren-001."
_MIGRATION_ID_DESCRIPTION = (
    "The migrationId dry_run_curriculum_migration gave for the manifest, e.g. migration_..."
)
_MANIFEST_DESCRIPTION = (
    "The migration manifest, as the console's migration import takes it: source, "
    "operatorNote and lessons. At most 4 MB as JSON. The stoa-admin MCP server also "
    "takes manifestPath, a local .json file it reads into this field, so the agent "
    "need not paste it."
)
_LESSON_LIST_DESCRIPTION = "publicLessonIds; at most 500."


def _lesson_ids(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    cleaned = [value.strip() for value in values]
    if any(not value for value in cleaned):
        raise ValueError("a publicLessonId must not be blank")
    return cleaned


class GetLessonStateArguments(_Arguments):
    publicLessonId: str = Field(min_length=1, max_length=160, description=_LESSON_ID_DESCRIPTION)
    auditLimit: int = Field(
        default=10, ge=0, le=50, description="How many of the newest lifecycle events to show."
    )


class GetMigrationArguments(_Arguments):
    migrationId: str = Field(min_length=1, max_length=64, description=_MIGRATION_ID_DESCRIPTION)


class DryRunCurriculumMigrationArguments(_Arguments):
    manifest: dict[str, Any] = Field(description=_MANIFEST_DESCRIPTION)


class ApplyCurriculumMigrationArguments(_Arguments):
    migrationId: str = Field(min_length=1, max_length=64, description=_MIGRATION_ID_DESCRIPTION)
    confirmationCode: str = Field(
        min_length=1,
        max_length=64,
        description="The confirmationCode the dry run gave for this same manifest.",
    )
    manifest: dict[str, Any] = Field(description=_MANIFEST_DESCRIPTION)
    confirmUpdates: list[str] = Field(
        default_factory=list,
        max_length=500,
        description=(
            "Required when the dry run listed `updates`: exactly those publicLessonIds, "
            "after the person agreed that each of those live lessons gets a new version. "
            "Leave empty when it listed none."
        ),
    )
    dryRun: bool = Field(strict=True, description=DRY_RUN_DESCRIPTION)

    @model_validator(mode="after")
    def _clean_updates(self) -> "ApplyCurriculumMigrationArguments":
        self.confirmUpdates = _lesson_ids(self.confirmUpdates) or []
        return self


class PublishCurriculumDraftsArguments(_Arguments):
    migrationId: str = Field(min_length=1, max_length=64, description=_MIGRATION_ID_DESCRIPTION)
    onlyLessonIds: list[str] | None = Field(
        default=None,
        max_length=500,
        description="Publish only these lessons of the migration. " + _LESSON_LIST_DESCRIPTION,
    )
    excludeLessonIds: list[str] = Field(
        default_factory=list,
        max_length=500,
        description="Leave these lessons of the migration out. " + _LESSON_LIST_DESCRIPTION,
    )
    confirmationCode: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Required when dryRun is false: the confirmationCode of the dry run the "
            "person agreed to. Refused if the plan changed since."
        ),
    )
    confirmReplacements: list[str] = Field(
        default_factory=list,
        max_length=500,
        description=(
            "Required when the dry run listed `replacements`: exactly those "
            "publicLessonIds, after the person agreed that each replaces the version "
            "students see now. Leave empty when it listed none."
        ),
    )
    dryRun: bool = Field(strict=True, description=DRY_RUN_DESCRIPTION)

    @model_validator(mode="after")
    def _clean_lists(self) -> "PublishCurriculumDraftsArguments":
        self.onlyLessonIds = _lesson_ids(self.onlyLessonIds)
        self.excludeLessonIds = _lesson_ids(self.excludeLessonIds) or []
        self.confirmReplacements = _lesson_ids(self.confirmReplacements) or []
        return self


class RollbackLessonArguments(_Arguments):
    publicLessonId: str = Field(min_length=1, max_length=160, description=_LESSON_ID_DESCRIPTION)
    versionId: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description=(
            "The version to put live again. Leave it out for the version that was live "
            "before the current one."
        ),
    )
    reason: str = Field(
        min_length=1,
        max_length=300,
        description="Why, e.g. 'Exercise 3 has a wrong answer key.' Kept in the lesson's audit.",
    )
    expectedPublishedVersionId: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "Required when dryRun is false: the live version the dry run showed. "
            "Refused if another version went live since."
        ),
    )
    dryRun: bool = Field(strict=True, description=DRY_RUN_DESCRIPTION)

    @model_validator(mode="after")
    def _reason_says_something(self) -> "RollbackLessonArguments":
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        return self


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
    OperationSpec(
        name="get_lesson_state",
        effect=Effect.READ,
        title="Show a curriculum lesson's versions",
        description=(
            "Read only. Shows one curriculum lesson, named by publicLessonId, as the "
            "console's curriculum desk does: the live version (publishedVersionId, the "
            "one students see, and the version that was live before it), every version "
            "with its state (draft, in_review, changes_requested, approved, published, "
            "superseded or archived), title, migration and last change, and the newest "
            "lifecycle events. Lesson content and exercises are not included. Every "
            "call is recorded in the audit trail."
        ),
        arguments=GetLessonStateArguments,
    ),
    OperationSpec(
        name="get_migration",
        effect=Effect.READ,
        title="Show a curriculum migration",
        description=(
            "Read only. Shows the record of an applied curriculum migration, named by "
            "migrationId: status, source, who applied it and when, the summary, and "
            "each row's lesson, action (create, update or skip), status and the "
            "version it wrote, with the version that was live before it. Every call is "
            "recorded in the audit trail."
        ),
        arguments=GetMigrationArguments,
    ),
    OperationSpec(
        name="dry_run_curriculum_migration",
        effect=Effect.READ,
        title="Check a curriculum migration manifest",
        description=(
            "Read only. Writes no content. Checks a migration manifest as the console's "
            "migration dry run does and answers with its migrationId and "
            "confirmationCode, a summary, and each row's action: create (a new lesson), "
            "update (a new version of a lesson that is live now), skip (content "
            "unchanged), error (validation issues) or conflict (expectedPublishedVersionId "
            "does not match). `updates` lists every update row with the version live "
            "now: show it to the person on its own, because applying writes a new "
            "version of each and publishing replaces what students see. "
            "`publishReady` is false while there are errors or conflicts. Every call is "
            "recorded in the audit trail."
        ),
        arguments=DryRunCurriculumMigrationArguments,
    ),
    OperationSpec(
        name="apply_curriculum_migration",
        effect=Effect.WRITE,
        title="Import a curriculum migration as drafts",
        description=(
            "Changes data. Before calling, confirm with the person: run "
            "dry_run_curriculum_migration (or this with dryRun=true), show them the "
            "summary and every row in `updates`, and only call with dryRun=false, "
            "passing the migrationId and confirmationCode of that dry run and, in "
            "confirmUpdates, exactly the lessons `updates` listed, once they have said "
            "yes. Imports the manifest as drafts: every create and update row becomes a "
            "new draft version, nothing goes live, and rows marked publish in the "
            "manifest are refused (publish with publish_curriculum_drafts instead). "
            "Refused while the manifest has errors or conflicts, when the code does "
            "not match the manifest, or when confirmUpdates is not exactly the update "
            "rows. Applying the same manifest again changes nothing and says so. Every "
            "call, dry runs included, is recorded in the audit trail with the migration."
        ),
        arguments=ApplyCurriculumMigrationArguments,
    ),
    OperationSpec(
        name="publish_curriculum_drafts",
        effect=Effect.WRITE,
        title="Publish a curriculum migration's drafts",
        description=(
            "Changes data. Students see the result. Before calling, confirm with the "
            "person: run with dryRun=true first, show them how many lessons would go "
            "live, which are skipped and why, and every row in `replacements`, and only "
            "call with dryRun=false, passing the dry run's confirmationCode and, in "
            "confirmReplacements, exactly the lessons `replacements` listed, once they "
            "have said yes. Moves the drafts an applied migration wrote (narrowed by "
            "onlyLessonIds and excludeLessonIds) through review, approval and "
            "publication, lesson after lesson, as the console's buttons do; a lesson "
            "already published, sent back for changes or failing validation is skipped. "
            "A replacement is published only if the version live when the migration "
            "was applied is still live. The first refusal, such as another version "
            "having gone live in between, stops the run there: the answer says which "
            "lessons were published and where it stopped; run the dry run again to go "
            "on. One call publishes at most 60 lessons and pauses after about 18 seconds, saying where; a new dry run goes on from there. Every call, dry runs included, is "
            "recorded in the audit trail with the migration and the lessons."
        ),
        arguments=PublishCurriculumDraftsArguments,
    ),
    OperationSpec(
        name="rollback_lesson",
        effect=Effect.WRITE,
        title="Roll back a curriculum lesson",
        description=(
            "Changes data. Students see the result. Before calling, confirm with the "
            "person: run with dryRun=true first, show them which version is live now "
            "and which would be live after, and only call with dryRun=false, passing "
            "the live version the dry run showed as expectedPublishedVersionId, once "
            "they have said yes. Puts an earlier version of one lesson live again, as "
            "the console's rollback does: by default the version that was live before "
            "the current one, or the versionId given. Refused if another version went "
            "live since the dry run. Every call, dry runs included, is recorded in the "
            "audit trail with its reason."
        ),
        arguments=RollbackLessonArguments,
        destructive=True,
    ),
)

OPERATIONS_BY_NAME: dict[str, OperationSpec] = {spec.name: spec for spec in OPERATIONS}
