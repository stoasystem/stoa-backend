"""The data type catalog: every kind of row, and which accounts it points to (#586, #587).

One entry per `entity_type` the code writes, in this one reviewed file. Each
entry declares:

- **The account pointers.** Every place a row of the type names an account,
  each with its role: `owner` (the row is that account's, and the account's
  deletion removes or tombstones it) or `reference` (the row only mentions the
  account, and its deletion scrubs the name out). A pointer is one of:

  - `Field("owner_id")`, `Field("metadata.student_id")`: a string at a path of
    nested maps;
  - `Ids("previous_dispatch_teacher_ids")`: a list or set of ids;
  - `Summaries("children")`: a map whose keys are ids, and/or whose entries (or
    a list of entries) carry `user_id` / `student_id` / `child_id`;
  - `KeyId("SK", "CHILD#")`: a key that is a prefix and then the id, which is
    also how a row with no owner attribute is owned by its key (`rate_counter`
    under `USAGE#{id}`, a sign-in under `USER#{id}`);
  - `ScopeId()`: a `scope` of `student:{id}` or `student/{id}` - never a bare
    id, which any scope string would pass for.

  A type that points to no account declares `accounts=()`; that is a decision
  too, and the gate in `tests/test_data_catalog.py` keeps it honest.
- **Fields that are not pointers.** An attribute the type's writers write that
  looks like an account id but is deliberately not handled (`created_by` on a
  link: usually an administrator, whose deletion must not sweep the links they
  issued), each with its reason. The writer gate fails on an account-looking
  attribute in neither list, so a new field name cannot slip past.
- **The deletion handling.** Empty for now; candidate I fills it (see #586).
- **The owning module** - where the type's rows are written.

`mentions(row)` and `names(row, account)` read one row against its entry and
nothing else. Ids are compared exactly as stored - no stripping - and a value
holding `#`, `:` or `/` is never an account id (the separators every key is
built with; an operator call signs its writes `operator:agent_mcp`), as in
`owner_registry.reference_put`.

A row is matched to its entry by `entity_type`. A few kinds of row are written
with none at all (the profile, a practice attempt, usage counters); those are
matched by their key shape (`UNTYPED`). A deletion tombstone whose type is
`{type}_deletion_tombstone` built from another type's name is matched by that
suffix. A row that matches nothing is unknown: `mentions` says it names no
account, because a caller walking the whole table (the sweep, a comparison
script) has to get through rows written before a type had a name; and
`mentions_strict` raises `UnknownDataType`, for a caller that must not guess.

Nothing in production reads this module yet: account deletion, the owner
registry and its sweep switch over to it in #588-#590. Until then
`tests/test_data_catalog.py` holds it to what they do today, difference by
difference.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Final, Literal

type Role = Literal["owner", "reference"]
OWNER: Final = "owner"
REFERENCE: Final = "reference"

type Lifecycle = Literal["written", "no_longer_written", "legacy"]
"""`written`: something in `src/stoa` writes it. `no_longer_written`: nothing does any
more, but stored rows may remain (the deletion still has to reach them).
`legacy`: older still, read by the deletion only; no writer in this codebase."""

_SEPARATORS: Final = ("#", ":", "/")
_SUMMARY_ENTRY_FIELDS: Final = ("user_id", "student_id", "child_id")
DELETION_TOMBSTONE_SUFFIX: Final = "_deletion_tombstone"


def is_account_id(value: object) -> bool:
    """Whether `value` can be an account id: a non-blank string with no key separator."""
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not any(separator in value for separator in _SEPARATORS)
    )


# -- pointers ---------------------------------------------------------------------------


def _at(row: Mapping[str, object], path: tuple[str, ...]) -> object:
    value: object = row
    for name in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(name)
    return value


@dataclass(frozen=True, slots=True)
class Field:
    """A string at a path of nested maps: `owner_id`, `metadata.student_id`."""

    path: str
    role: Role

    @property
    def attribute(self) -> str:
        return self.path

    def values(self, row: Mapping[str, object]) -> Iterator[object]:
        yield _at(row, tuple(self.path.split(".")))


@dataclass(frozen=True, slots=True)
class Ids:
    """A list or set of ids: `previous_dispatch_teacher_ids`."""

    path: str
    role: Role

    @property
    def attribute(self) -> str:
        return self.path

    def values(self, row: Mapping[str, object]) -> Iterator[object]:
        value = _at(row, tuple(self.path.split(".")))
        if isinstance(value, (list, tuple, set, frozenset)):
            yield from value


@dataclass(frozen=True, slots=True)
class Summaries:
    """Per-account summaries: a map keyed by id, its entries (or a list's) carrying ids."""

    path: str
    role: Role

    @property
    def attribute(self) -> str:
        return self.path

    def values(self, row: Mapping[str, object]) -> Iterator[object]:
        value = _at(row, tuple(self.path.split(".")))
        entries: tuple[object, ...] = ()
        if isinstance(value, Mapping):
            yield from value.keys()
            entries = tuple(value.values())
        elif isinstance(value, (list, tuple)):
            entries = tuple(value)
        for entry in entries:
            if isinstance(entry, Mapping):
                for name in _SUMMARY_ENTRY_FIELDS:
                    yield entry.get(name)


@dataclass(frozen=True, slots=True)
class KeyId:
    """A key that is `prefix` and then the id: `SK = CHILD#{id}`, `PK = USAGE#{id}`."""

    key: Literal["PK", "SK"]
    prefix: str
    role: Role

    @property
    def attribute(self) -> str:
        return self.key

    def values(self, row: Mapping[str, object]) -> Iterator[object]:
        value = row.get(self.key)
        if isinstance(value, str) and value.startswith(self.prefix):
            yield value[len(self.prefix) :]


@dataclass(frozen=True, slots=True)
class ScopeId:
    """A `scope` naming a student: `student:{id}` or `student/{id}`, never a bare id."""

    role: Role
    prefixes: tuple[str, ...] = ("student:", "student/")

    @property
    def attribute(self) -> str:
        return "scope"

    def values(self, row: Mapping[str, object]) -> Iterator[object]:
        value = row.get("scope")
        if isinstance(value, str):
            for prefix in self.prefixes:
                if value.startswith(prefix):
                    yield value[len(prefix) :]


type Pointer = Field | Ids | Summaries | KeyId | ScopeId


@dataclass(frozen=True, slots=True)
class NotPointer:
    """An attribute that looks like an account id and is deliberately not a pointer."""

    attribute: str
    reason: str


@dataclass(frozen=True, slots=True)
class KeyShape:
    """How a row written without an `entity_type` is recognized: by its key."""

    pk_prefix: str
    sk: str | None = None  # the whole SK, when one value identifies the kind
    sk_prefix: str | None = None

    def matches(self, row: Mapping[str, object]) -> bool:
        pk, sk = row.get("PK"), row.get("SK")
        if not isinstance(pk, str) or not pk.startswith(self.pk_prefix):
            return False
        if not isinstance(sk, str):
            return False
        if self.sk is not None and sk != self.sk:
            return False
        return self.sk_prefix is None or sk.startswith(self.sk_prefix)


@dataclass(frozen=True, slots=True)
class DataType:
    """One kind of row: where it is written, and which accounts it points to."""

    name: str
    """Its `entity_type`; for an `UNTYPED` kind, a name of the catalog's own."""
    module: str
    """Where its rows are written (or, for a legacy kind, read)."""
    accounts: tuple[Pointer, ...]
    not_pointers: tuple[NotPointer, ...] = ()
    deletion: None = None
    """How account deletion handles it: filled by candidate I (see #586)."""
    lifecycle: Lifecycle = "written"
    untyped_key: KeyShape | None = None
    """Set only for a kind written with no `entity_type`."""


class UnknownDataType(LookupError):
    """A row whose kind the catalog does not list."""


# -- shorthands for the entries below -------------------------------------------------


def _owner(*paths: str) -> tuple[Field, ...]:
    return tuple(Field(path, OWNER) for path in paths)


def _reference(*paths: str) -> tuple[Field, ...]:
    return tuple(Field(path, REFERENCE) for path in paths)


def _owned_by_partition(prefix: str) -> KeyId:
    return KeyId("PK", prefix, OWNER)


def _not(reason: str, *attributes: str) -> tuple[NotPointer, ...]:
    return tuple(NotPointer(attribute, reason) for attribute in attributes)


_BILLING = (
    "billing, excluded from deletion as `subscription_billing_accounting`; no rule "
    "matches it today"
)
_ADMIN = "the administrator or operator who made the change; their deletion leaves it"
_NO_CALLER = (
    "nothing in src/stoa calls its writer (KEPT no_caller); declare its pointers when "
    "something does"
)
_REPOSITORIES = "stoa.db.repositories"


def _repo(name: str) -> str:
    return f"{_REPOSITORIES}.{name}"


# -- the catalog ------------------------------------------------------------------------

_ENTRIES: tuple[DataType, ...] = (
    # -- account and identity ----------------------------------------------------------
    DataType(
        "account_deletion_command", _repo("account_deletion_repo"), _owner("user_id")
    ),
    DataType(
        "account_deletion_pending",
        _repo("account_deletion_repo"),
        (),
        _not(
            "deletion bookkeeping: names the account under an attribute of its own so "
            "that no matcher takes it (`_pending_registry_item`)",
            "deletion_user_id",
        ),
    ),
    DataType("account_deletion_scan_cursor", _repo("account_deletion_repo"), ()),
    DataType(
        "account_email_claim",
        _repo("account_email_claim_repo"),
        (),
        _not(
            "released by the profile's deletion tombstone in the same transaction "
            "(`_email_claim_release`), found from the profile; `user_repo` registers it "
            "by hand only so the sweep stops reporting it (#586 decision 1)",
            "account_id",
        ),
    ),
    DataType("account_fence", _repo("account_deletion_repo"), _owner("user_id")),
    DataType(
        "account_invitation",
        _repo("account_invitation_repo"),
        _owner("account_id"),
        _not(
            "the inviter, usually an administrator, whose deletion must not sweep the "
            "invitations they issued; registered by hand only so the sweep stops "
            "reporting it (#586 decision 1)",
            "invited_by",
        ),
    ),
    DataType("account_invitation_pointer", _repo("account_invitation_repo"), ()),
    DataType(
        "account_number",
        _repo("account_number_repo"),
        (),
        _not(
            "a number is claimed for good so it is never handed to another account (KEPT); "
            "`account_provisioning_service` registers it by hand only so the sweep stops "
            "reporting it (#586 decision 1)",
            "account_id",
        ),
    ),
    DataType("account_number_sequence", _repo("account_number_repo"), ()),
    DataType("auth_sign_in_revocation", _repo("identity_repo"), ()),
    # `USER#{id}/SIGNIN#...`: no owner attribute; the account is its partition.
    DataType("auth_sign_in_session", _repo("identity_repo"), (_owned_by_partition("USER#"),)),
    DataType(
        "identity_binding",
        _repo("identity_repo"),
        _owner("user_id"),
        _not("who bound the identity (the account itself, or an operator)", "created_by"),
    ),
    DataType("identity_deletion_evidence", _repo("account_deletion_repo"), ()),
    DataType("provider_identity_revoke_debt", _repo("account_deletion_repo"), _owner("user_id")),
    DataType("public_identity_command", _repo("public_identity_repo"), _owner("user_id")),
    DataType("user_identity_inventory", _repo("identity_repo"), _owner("user_id")),
    DataType(
        "privileged_identity_command",
        _repo("privileged_identity_repo"),
        (),
        _not(_ADMIN, "approved_by"),
    ),
    DataType("teacher_seen", _repo("user_repo"), _owner("user_id")),
    DataType("password_change_code", "stoa.services.password_change_code_service", ()),
    DataType("password_change_send_quota", "stoa.services.password_change_code_service", ()),
    DataType("invitation_claim_throttle", "stoa.routers.auth", ()),
    DataType("parent_link_request_quota", "stoa.routers.parents", ()),
    DataType(
        "parent_student_link",
        _repo("parent_link_repo"),
        (
            *_owner("student_id", "parent_id"),
            # The forward row is PARENT#{parent}/CHILD#{student}, the reverse
            # STUDENT#{student}/PARENT#{parent}.
            KeyId("SK", "CHILD#", OWNER),
            KeyId("SK", "PARENT#", OWNER),
        ),
        _not(
            "usually an administrator, whose deletion must not sweep the links they issued",
            "created_by",
            "updated_by",
        ),
    ),
    DataType(
        "capability_grant_current",
        _repo("capability_repo"),
        (*_owner("user_id"), ScopeId(OWNER)),
        _not(_ADMIN, "updated_by"),
    ),
    DataType(
        "capability_grant_revision",
        _repo("capability_repo"),
        (*_owner("user_id"), ScopeId(OWNER)),
        _not(_ADMIN, "updated_by", "grantor_id"),
    ),
    # -- the owner registry and the sweep ----------------------------------------------
    DataType(
        "owner_registry",
        "stoa.db.owner_registry",
        (),
        _not(
            "bookkeeping: names the account only through its key and `registry_account`, "
            "and is removed with the account's partition (`delete_owner_registry`)",
            "registry_account",
        ),
    ),
    DataType("owner_registry_sweep_run", "stoa.services.owner_registry_sweep", ()),
    # -- usage, allowances and periods -------------------------------------------------
    DataType("allowance_counter", _repo("weekly_counter"), _owner("beneficiary_id")),
    DataType("allowance_effect", _repo("allowance_repo"), _owner("beneficiary_id")),
    DataType("provider_usage_evidence", _repo("allowance_repo"), _owner("beneficiary_id")),
    DataType(
        "teacher_support_admission",
        "stoa.services.teacher_support_allowance_service",
        _owner("beneficiary_id"),
        _not(
            "the paying parent: a parent's deletion leaves the child's allowance as it "
            "leaves the child's other rows",
            "parent_id",
        ),
    ),
    DataType(
        "teacher_support_assigned_allowance",
        "stoa.services.teacher_support_allowance_service",
        _owner("student_id"),
        _not(_ADMIN, "updated_by"),
    ),
    # Under a digest of the support scope; names no account.
    DataType("teacher_support_counter", _repo("weekly_counter"), ()),
    DataType(
        "usage_period_record",
        "stoa.services.usage_period",
        _owner("user_id"),
        _not(
            "the administrator who set the period; registered by hand only so the "
            "sweep stops reporting it (#586 decision 1)",
            "actor_id",
        ),
    ),
    DataType(
        "usage_ledger_event",
        "stoa.services.usage_ledger_service",
        (*_owner("student_id", "owner_id"), _owned_by_partition("USAGE_LEDGER#")),
        (
            *_not(
                "who caused the usage (the student, or someone acting for them); "
                "a mention only, not registered (#586 decision 1)",
                "actor_id",
            ),
            *_not(
                "the paying parent: usage accounting stays with the student",
                "parent_id",
            ),
        ),
    ),
    DataType(
        "rate_admission_operation",
        "stoa.services.rate_limit",
        (*_owner("owner_id"), _owned_by_partition("USAGE#")),
    ),
    # `USAGE#{id}`: the practice branch takes it by its partition.
    DataType(
        "rate_counter",
        "stoa.services.rate_limit",
        (*_owner("owner_id"), _owned_by_partition("USAGE#")),
    ),
    DataType("source_rate_window", "stoa.services.rate_limit", ()),
    DataType(
        "voice_question_consent",
        _repo("voice_question_consent_repo"),
        _owner("student_id"),
        _not(
            "the parent who changed it: a parent's deletion leaves the child's consent (#476)",
            "changed_by",
        ),
    ),
    DataType(
        "voice_question_consent_change",
        _repo("voice_question_consent_repo"),
        _owner("student_id"),
        _not(
            "the parent who changed it: a parent's deletion leaves the child's consent (#476)",
            "changed_by",
        ),
    ),
    DataType(
        "voice_transcription_day", _repo("voice_transcription_usage_repo"), _owner("student_id")
    ),
    # -- billing (excluded from deletion) ----------------------------------------------
    DataType("allowance_plan", _repo("billing_fact_repo"), (), _not(_BILLING, "parent_id")),
    DataType(
        "beneficiary_grant",
        _repo("billing_fact_repo"),
        (),
        _not(_BILLING, "parent_id", "beneficiary_id"),
    ),
    DataType(
        "billing_activation_receipt", _repo("billing_fact_repo"), (), _not(_BILLING, "parent_id")
    ),
    DataType("billing_event_inbox", _repo("billing_fact_repo"), ()),
    DataType("billing_object_fact", _repo("billing_fact_repo"), ()),
    DataType("billing_projection", _repo("billing_fact_repo"), (), _not(_BILLING, "parent_id")),
    DataType("billing_reconciliation_lease", _repo("billing_fact_repo"), ()),
    DataType("billing_semantic_dedupe", _repo("billing_fact_repo"), ()),
    DataType(
        "checkout_command",
        _repo("checkout_command_repo"),
        (),
        _not(_BILLING, "parent_id", "beneficiary_ids"),
    ),
    DataType(
        "checkout_open_guard", _repo("checkout_command_repo"), (), _not(_BILLING, "parent_id")
    ),
    DataType(
        "checkout_public_lookup", _repo("checkout_command_repo"), (), _not(_BILLING, "parent_id")
    ),
    DataType(
        "paid_grant_history",
        "stoa.services.paid_entitlement_service",
        (),
        _not(_BILLING, "parent_id", "beneficiary_id"),
    ),
    DataType(
        "paid_transition",
        "stoa.services.paid_entitlement_service",
        (),
        _not(_BILLING, "parent_id", "beneficiary_ids"),
    ),
    DataType(
        "subscription_billing",
        "stoa.services.subscription_service",
        (),
        (*_not(_BILLING, "parent_id"), *_not(_ADMIN, "manual_override_by")),
    ),
    DataType(
        "subscription_billing_event",
        "stoa.services.subscription_service",
        (),
        _not(_BILLING, "parent_id"),
    ),
    DataType(
        "subscription_billing_event_dedupe",
        "stoa.services.subscription_service",
        (),
        _not(_BILLING, "parent_id"),
    ),
    DataType(
        "subscription_billing_provider_lookup",
        "stoa.services.subscription_service",
        (),
        _not(_BILLING, "parent_id"),
    ),
    DataType(
        "subscription_billing_refund_idempotency",
        "stoa.services.subscription_service",
        (),
        (*_not(_BILLING, "parent_id"), *_not(_ADMIN, "actor")),
    ),
    DataType(
        "subscription_payment_rollout",
        "stoa.services.subscription_service",
        (),
        _not(_ADMIN, "updated_by"),
    ),
    # Its `student_id` is matched today, though no branch acts on it (KEPT).
    DataType(
        "subscription_request",
        "stoa.services.subscription_service",
        _owner("student_id"),
        (*_not(_BILLING, "parent_id"), *_not(_ADMIN, "applied_by")),
    ),
    DataType(
        "subscription_request_event",
        "stoa.services.subscription_service",
        (),
        _not(_BILLING + " (who changed the request: the parent or an administrator)", "actor_id"),
    ),
    DataType(
        "subscription_request_open_guard",
        "stoa.services.subscription_service",
        (),
        _not(_BILLING, "parent_id"),
    ),
    # -- teacher applications (excluded from deletion) ---------------------------------
    # The activation command carries the new teacher's `user_id`, matched today;
    # it stays on purpose (KEPT).
    DataType("teacher_activation_command", _repo("teacher_application_repo"), _owner("user_id")),
    DataType("teacher_activation_invitation", _repo("teacher_application_repo"), ()),
    DataType(
        "teacher_application_review",
        _repo("teacher_application_repo"),
        (),
        _not(_ADMIN, "reviewer_id"),
    ),
    DataType("teacher_application_version", _repo("teacher_application_repo"), ()),
    # -- security audit and analytics (no account's data) ------------------------------
    DataType("security_audit_event", _repo("security_audit_repo"), ()),
    DataType("authorization_probe_aggregate", _repo("security_audit_repo"), ()),
    DataType("analytics_event", "stoa.routers.analytics", ()),
    DataType("knowledge_gap", _repo("knowledge_gap_repo"), ()),
    # -- curriculum ---------------------------------------------------------------------
    DataType("curriculum_analytics_metric", _repo("curriculum_analytics_repo"), ()),
    # Owned through its owner manifest. Signals written before the manifest
    # name the student only as `metadata.studentHash`, a hash; deletion matched
    # them by it, which the catalog drops (#586 decision 3: 0 such rows in
    # production on 2026-11-23).
    DataType("curriculum_analytics_signal", _repo("curriculum_analytics_repo"), ()),
    DataType(
        "curriculum_signal_owner_manifest",
        _repo("curriculum_analytics_repo"),
        (_owned_by_partition("CURRICULUM_SIGNAL_OWNER#"),),
    ),
    DataType("curriculum_signal_reconciliation", _repo("curriculum_analytics_repo"), ()),
    DataType("curriculum_audit_event", _repo("curriculum_ops_repo"), ()),
    DataType("curriculum_migration_evidence", _repo("curriculum_ops_repo"), ()),
    DataType("curriculum_pointer", _repo("curriculum_ops_repo"), (), _not(_ADMIN, "updated_by")),
    DataType("curriculum_publish_manifest", _repo("curriculum_ops_repo"), ()),
    DataType("curriculum_version", _repo("curriculum_ops_repo"), ()),
    DataType("practice_challenge_pointer", _repo("practice_repo"), ()),
    # -- conversations, attachments, uploads -------------------------------------------
    DataType(
        "conversation", "stoa.services.learning_session", _owner("student_id", "owner_id")
    ),
    DataType(
        "conversation_message",
        "stoa.services.learning_session._write",
        _owner("owner_id", "student_id"),
    ),
    DataType(
        "conversation_teacher_note",
        "stoa.services.help_requests",
        _owner("owner_id", "student_id"),
        _not(
            "GAP: no rule matches it today - a teacher's deletion leaves their notes, and "
            "`teacher_name`, in the student's conversation; decide with candidate I",
            "teacher_id",
        ),
    ),
    DataType(
        "message_command",
        "stoa.services.ask_question._answering",
        _owner("owner_id", "student_id"),
    ),
    DataType(
        "chat_quota_operation",
        "stoa.services.ask_question._store",
        (*_owner("owner_id"), _owned_by_partition("USAGE#")),
    ),
    DataType(
        "help_request",
        "stoa.services.help_requests",
        (
            *_owner("owner_id", "student_id"),
            # A student's request names the teacher it is with, the one it is
            # offered to, the ones who let it lapse (#189) and the ones who
            # declined it (#391). Set by updates, which the writer gate cannot see.
            *_reference("teacher_id", "dispatched_teacher_id"),
            Ids("previous_dispatch_teacher_ids", REFERENCE),
            Ids("declined_dispatch_teacher_ids", REFERENCE),
        ),
    ),
    DataType(
        "asked_knowledge_points", _repo("asked_knowledge_repo"), _owner("owner_id", "student_id")
    ),
    DataType("attachment", "stoa.services.attachment_service", _owner("owner_id", "student_id")),
    DataType(
        "attachment_association",
        "stoa.services.attachment_service",
        _owner("owner_id", "student_id"),
    ),
    DataType("attachment_retention_fence", _repo("attachment_repo"), _owner("owner_id")),
    DataType(
        "upload_intent", "stoa.services.uploads._lifecycle", _owner("owner_id", "student_id")
    ),
    DataType("upload_code", _repo("upload_code_repo"), _owner("owner_id")),
    # -- moderation ---------------------------------------------------------------------
    # Owned by the row's own `student_id` (#586 decision 3); looking the owner
    # up through the question (`_resolve_private_owner`) is a deletion-time check.
    DataType(
        "moderation_case",
        _repo("moderation_repo"),
        _owner("student_id"),
        (
            *_not("the administrator handling the case", "assigned_admin_id"),
            *_not(
                "who reported it; no rule matches it today (decide with candidate I)",
                "reporter_id",
            ),
        ),
    ),
    DataType(
        "moderation_event",
        _repo("moderation_repo"),
        _owner("student_id"),
        _not(_ADMIN, "actor_id"),
    ),
    # -- reports ------------------------------------------------------------------------
    DataType(
        "REPORT_AUDIT_EVENT",
        _repo("report_repo"),
        _owner("student_id", "owner_id"),
        (
            *_not(
                "GAP: the parent the report went to; no rule matches it today - a parent's "
                "deletion leaves the audit events naming them (decide with candidate I)",
                "parent_id",
            ),
            *_not(_ADMIN, "actor"),
        ),
    ),
    # An operator's job: no top-level owner; the job's filters can name a
    # student or parent (`report_repo._recovery_job_record_accounts`).
    DataType(
        "REPORT_RECOVERY_JOB",
        _repo("report_repo"),
        _owner("student_id", "owner_id", "filters.student_id", "filters.parent_id"),
        _not(_ADMIN, "created_by", "requested_by"),
    ),
    DataType(
        "REPORT_RECOVERY_JOB_AUDIT_EVENT",
        _repo("report_repo"),
        _owner(
            "student_id",
            "owner_id",
            "metadata.student_id",
            "metadata.parent_id",
            "metadata.filters.student_id",
            "metadata.filters.parent_id",
        ),
        _not(_ADMIN, "actor"),
    ),
    DataType(
        "REPORT_RECOVERY_JOB_TARGET",
        _repo("report_repo"),
        _owner("student_id", "owner_id"),
        _not(
            "GAP: the parent the report went to; no rule matches it today - a parent's "
            "deletion leaves the targets naming them (decide with candidate I)",
            "parent_id",
        ),
    ),
    DataType("report_email_intent", _repo("report_repo"), _owner("owner_id")),
    DataType("report_object_intent", _repo("report_repo"), _owner("owner_id")),
    DataType("AUDIT_RETENTION_EVENT", _repo("report_repo"), ()),
    DataType("AUDIT_RETENTION_IMMUTABLE_MANIFEST", _repo("report_repo"), ()),
    DataType("LEGAL_HOLD_AUDIT_EVENT", _repo("report_repo"), ()),
    DataType("LEGAL_HOLD_METADATA", _repo("report_repo"), ()),
    DataType("LEGAL_HOLD_REVIEW_METADATA", _repo("report_repo"), ()),
    DataType("REPORT_ARTIFACT_EDIT_DRAFT", _repo("report_repo"), ()),
    DataType("REPORT_ARTIFACT_ROLLBACK_PREVIEW", _repo("report_repo"), ()),
    DataType("REPORT_EDIT_DRAFT", _repo("report_repo"), ()),
    DataType("RETENTION_APPROVAL_AUDIT_EVENT", _repo("report_repo"), ()),
    DataType("RETENTION_APPROVAL_METADATA", _repo("report_repo"), ()),
    DataType("SUPPORT_CRM_MESSAGE_EVENT", _repo("report_repo"), ()),
    DataType("SUPPORT_CRM_MESSAGE_FEED", _repo("report_repo"), ()),
    DataType("SUPPORT_HANDOFF_AUDIT_EVENT", _repo("report_repo"), ()),
    DataType("SUPPORT_HANDOFF_DELIVERY", _repo("report_repo"), (), _not(_ADMIN, "actor")),
    DataType("SUPPORT_HANDOFF_DELIVERY_AUDIT_EVENT", _repo("report_repo"), ()),
    DataType("SUPPORT_HANDOFF_DELIVERY_FEED", _repo("report_repo"), ()),
    # -- practice and learning ----------------------------------------------------------
    DataType(
        "practice_progress",
        _repo("practice_repo"),
        (*_owner("student_id", "owner_id"), _owned_by_partition("PROGRESS#")),
    ),
    DataType(
        "study_day",
        _repo("practice_repo"),
        (*_owner("student_id", "user_id", "owner_id"), _owned_by_partition("ACTIVITY#")),
    ),
    DataType(
        "lit_unit",
        _repo("practice_repo"),
        (*_owner("student_id", "user_id"), _owned_by_partition("ACTIVITY#")),
    ),
    DataType(
        "lit_ledger",
        _repo("practice_repo"),
        (*_owner("student_id", "user_id"), _owned_by_partition("ACTIVITY#")),
    ),
    DataType(
        "practice_quiz_paper",
        _repo("practice_repo"),
        (*_owner("student_id"), _owned_by_partition("QUIZ#")),
    ),
    DataType(
        "practice_quiz_credential",
        _repo("practice_repo"),
        (*_owner("student_id"), _owned_by_partition("QUIZ#")),
    ),
    DataType(
        "practice_star_quiz_cooldown",
        _repo("practice_repo"),
        (*_owner("student_id"), _owned_by_partition("QUIZ#")),
    ),
    DataType(
        "practice_star_quiz_pass",
        _repo("practice_repo"),
        (*_owner("student_id"), _owned_by_partition("QUIZ#")),
    ),
    DataType(
        "review_card",
        _repo("review_repo"),
        (*_owner("student_id", "user_id"), _owned_by_partition("REVIEW#")),
    ),
    DataType("practice_deletion_tombstone", _repo("practice_repo"), ()),
    DataType("practice_accounting_tombstone", _repo("practice_repo"), ()),
    DataType(
        "learning_assignment",
        _repo("adaptive_learning_repo"),
        _owner("student_id", "owner_id"),
        _not(
            "who assigned it (a teacher, parent or administrator); their deletion leaves "
            "the student's assignments",
            "created_by",
        ),
    ),
    DataType(
        "learning_memory_snapshot",
        _repo("adaptive_learning_repo"),
        (*_owner("student_id", "owner_id"), _owned_by_partition("LEARNING_MEMORY#")),
    ),
    DataType("ai_teacher_draft_deletion_tombstone", _repo("ai_teacher_tools_repo"), ()),
    DataType("teacher_session_deletion_tombstone", _repo("account_deletion_repo"), ()),
    # -- notifications and realtime -----------------------------------------------------
    DataType(
        "notification_event",
        "stoa.services.notification_service",
        (
            *_owner("owner_id"),
            *_reference("actor_id"),
            # In `metadata`, the accounts it is about, whose deletion tombstones
            # it like its recipient's, and the ones it only mentions, scrubbed
            # out of it (#574; `account_deletion_repo.NOTIFICATION_*_FIELDS`).
            *_owner("metadata.owner_id", "metadata.student_id"),
            *_reference("metadata.actor_id", "metadata.teacher_id", "metadata.parent_id"),
        ),
        _not(
            "GAP: who it went to when that is not its owner (a parent told about a child, "
            "a teacher); no rule matches it today - the sweep counts it as an unmatched "
            "mention (decide with candidate I)",
            "recipient_id",
        ),
    ),
    DataType(
        "notification_preference",
        "stoa.services.notification_service",
        _owner("owner_id", "user_id"),
    ),
    DataType(
        "notification_push_token",
        "stoa.services.notification_service",
        _owner("owner_id", "user_id"),
    ),
    DataType("notification_delivery_intent", _repo("notification_repo"), _owner("owner_id")),
    DataType(
        "payment_expiry_reminder",
        _repo("notification_repo"),
        _owner("owner_id"),
        _not("the same account as `owner_id`, which is declared", "parent_id"),
    ),
    DataType(
        "websocket_connection", "stoa.services.websocket_service", _owner("owner_id", "user_id")
    ),
    # -- no longer written: stored rows may remain, and the deletion still reaches them -
    DataType(
        "teacher_assistance_summary_seed",
        _repo("notification_repo"),
        _owner("owner_id", "student_id"),
        lifecycle="no_longer_written",
    ),
    DataType(
        "ai_teacher_draft",
        _repo("ai_teacher_tools_repo"),
        _owner("student_id", "owner_id"),
        lifecycle="no_longer_written",
    ),
    # -- legacy: no writer in this codebase; the deletion still reads them --------------
    DataType(
        "question",
        _repo("account_deletion_repo"),
        (
            *_owner("student_id"),
            *_reference("teacher_id", "dispatched_teacher_id"),
            Ids("previous_dispatch_teacher_ids", REFERENCE),
        ),
        lifecycle="legacy",
    ),
    # A teacher's deletion tombstones the session (`replace_teacher_session_with_tombstone`).
    DataType(
        "teacher_session",
        _repo("account_deletion_repo"),
        _owner("student_id", "teacher_id"),
        lifecycle="legacy",
    ),
    DataType(
        "teacher_escalation_intent",
        _repo("account_deletion_repo"),
        _owner("student_id"),
        lifecycle="legacy",
    ),
)

# Kinds of row written with no `entity_type`, recognized by their key.
UNTYPED: tuple[DataType, ...] = (
    DataType(
        "user_profile",
        _repo("user_repo"),
        (
            *_owner("user_id"),
            # A parent's profile can still name a child the old way; the
            # child's deletion scrubs them out (`scrub_parent_profile_child`).
            *_reference("child_user_id", "student_id", "child_id"),
            Summaries("children", REFERENCE),
            Summaries("child_summaries", REFERENCE),
            Summaries("student_summaries", REFERENCE),
        ),
        _not(
            "who opened the account, usually an administrator; registered by hand only so "
            "the sweep stops reporting it (#586 decision 1)",
            "created_by",
        ),
        untyped_key=KeyShape("USER#", sk="PROFILE"),
    ),
    DataType(
        "practice_attempt",
        _repo("practice_repo"),
        (*_owner("student_id", "user_id"), _owned_by_partition("ATTEMPTS#")),
        untyped_key=KeyShape("ATTEMPTS#"),
    ),
    # The daily question and chat counters (`USAGE#{id}/QUESTION#{day}`, `CHAT#...`).
    DataType(
        "usage_counter",
        _repo("usage_ledger_repo"),
        (*_owner("owner_id", "student_id"), _owned_by_partition("USAGE#")),
        untyped_key=KeyShape("USAGE#"),
    ),
    # The attachment quota row, the last one the attachment purge deletes.
    DataType(
        "attachment_storage_usage",
        _repo("attachment_repo"),
        (_owned_by_partition("STORAGE#"),),
        untyped_key=KeyShape("STORAGE#", sk="USAGE"),
    ),
    DataType(
        "report_summary",
        _repo("report_repo"),
        _owner("student_id", "owner_id"),
        _not(
            "GAP: the parent the report went to; no rule matches it today (decide with "
            "candidate I)",
            "parent_id",
        ),
        untyped_key=KeyShape("REPORT#", sk="SUMMARY"),
    ),
)

# What a deletion leaves in place of a row and names after it,
# `{entity_type}_deletion_tombstone`: a status, a generation and timestamps,
# never an account (`account_deletion_repo`, `adaptive_learning_repo`,
# `notification_repo` build them).
DELETION_TOMBSTONES: Final = DataType(
    f"*{DELETION_TOMBSTONE_SUFFIX}", _repo("account_deletion_repo"), ()
)

CATALOG: Final[Mapping[str, DataType]] = {entry.name: entry for entry in _ENTRIES}
if len(CATALOG) != len(_ENTRIES):  # pragma: no cover - a duplicate entry is a typo
    raise RuntimeError("an entity_type is listed twice in the data type catalog")


def data_type_of(row: Mapping[str, object]) -> DataType | None:
    """The catalog entry for `row`: by its `entity_type`, else by its key; None if unknown."""
    entity_type = row.get("entity_type")
    if isinstance(entity_type, str) and entity_type:
        found = CATALOG.get(entity_type)
        if found is None and entity_type.endswith(DELETION_TOMBSTONE_SUFFIX):
            return DELETION_TOMBSTONES
        return found
    if entity_type not in (None, ""):
        return None
    return next(
        (entry for entry in UNTYPED if entry.untyped_key and entry.untyped_key.matches(row)),
        None,
    )


def _mentions(entry: DataType, row: Mapping[str, object]) -> dict[str, Role]:
    found: dict[str, Role] = {}
    for pointer in entry.accounts:
        for value in pointer.values(row):
            if isinstance(value, str) and is_account_id(value) and found.get(value) != OWNER:
                found[value] = pointer.role
    return found


def mentions(row: Mapping[str, object]) -> dict[str, Role]:
    """Every account `row` points to, with its role (`owner` wins over `reference`).

    A row whose kind the catalog does not know names no account here; see
    `mentions_strict`.
    """
    entry = data_type_of(row)
    return {} if entry is None else _mentions(entry, row)


def mentions_strict(row: Mapping[str, object]) -> dict[str, Role]:
    """`mentions`, refusing a row whose kind the catalog does not know."""
    entry = data_type_of(row)
    if entry is None:
        raise UnknownDataType(str(row.get("entity_type") or "(no entity_type)"))
    return _mentions(entry, row)


def names(row: Mapping[str, object], account: str) -> bool:
    """Whether `row` points to `account`, in either role. `account` must be an account id."""
    if not is_account_id(account):
        raise ValueError("not an account id")
    return account in mentions(row)
