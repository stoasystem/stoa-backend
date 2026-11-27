"""Every kind of row the code writes is deleted by a branch, or kept on purpose (#534).

Account deletion first *finds* an account's rows - its derived partitions and
the ones registered under it, which `test_owner_registry_unfenced_writers`
keeps honest - and then runs each branch in
`account_deletion_service.BRANCH_HANDLERS` over them. Each branch picks the
rows it acts on by its own test: an `entity_type`, a key prefix, an owner
field. A row no branch picks outlives the account, and nothing failed. Voice
consent (#476) and the daily transcription counter (#477) were added to a
branch by hand; this test is there for the next kind of row.

It works by `entity_type`, the name every kind of row is written with:

1. `written_entity_types` (`entity_type_scan`, shared with the data type
   catalog gates, #587) reads `src/stoa` and collects every `entity_type` a
   row can be written with: the value under an `"entity_type"` key of a dict
   literal, an `entity_type=` keyword argument, and the value an update sets
   with `SET entity_type = :x`. A name or `module.NAME` is resolved to the
   string it stands for, and `a if c else b` to both. A writer whose value it
   cannot resolve (an f-string, a parameter) must be in `UNRESOLVED_WRITERS`,
   saying what it writes.
2. Each type the catalog (`stoa.db.data_catalog`) says points to an account,
   and does not keep, is listed in `deleted_by_branch()` with the branch that
   picks it and one row of that type belonging to the account, keyed the way
   its writer keys it. A type that points to no account, or that the catalog
   keeps (`Keep`, with its reason), is not listed (#639). A listed type the
   code no longer writes fails as stale, unless it is in `NO_LONGER_WRITTEN`:
   rows the code stopped writing but that may still be stored, so their branch
   still has to delete them. Such a type stays in `deleted_by_branch()` with a
   row keyed as its old writer keyed it, and fails if anything writes it again.
3. The `deleted_by_branch()` rows are stored and every branch is run over the
   account the way a registry-path deletion runs it, with the branches' row
   operations replaced by a recorder. Each row must reach the branch it is
   listed under, so a listing cannot name a branch that does not pick the row.
   A branch that acts on rows through an operation the recorder does not
   replace (`picks_by_branch`) records nothing: add the operation there.
4. What the catalog says a type's deletion does (`DataType.deletion`, #639) is
   what the branch that picks it does: deletes the row, or replaces it with a
   tombstone of exactly its family's allowlist (`FAMILY_ACTIONS`).

A new kind of row therefore fails here until someone decides: make a branch
pick it and list it with a row of its shape, or say in the catalog that it
points to no account or why it is kept. Rows written with no `entity_type` at
all are outside the first three; the fourth covers them by name
(`HANDLED_UNLISTED`).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from entity_type_scan import ROOT, written_entity_types


# Writers whose `entity_type` the scan cannot resolve, and what they write.
UNRESOLVED_WRITERS: dict[str, str] = {
    # `{entity}_deletion_tombstone`, `{entity_type}_deletion_tombstone`: the
    # tombstones the deletion leaves in place of what it removed.
    "src/stoa/db/repositories/account_deletion_repo.py::replace_with_deletion_tombstone": (
        "deletion_flow"
    ),
    "src/stoa/db/repositories/adaptive_learning_repo.py::scrub_adaptive_private_row": (
        "deletion_flow"
    ),
    "src/stoa/db/repositories/notification_repo.py::_replace_notification_owner_tombstone": (
        "deletion_flow"
    ),
    # A parameter: its callers pass `entity_type="billing_projection"` and the
    # like, which the scan reads at the call.
    "src/stoa/db/repositories/billing_fact_repo.py::_activation_item": "keyword_at_callers",
    # `kind.entity_type`: the `CounterKind(entity_type=...)` constants in the
    # same module, which the scan reads.
    "src/stoa/db/repositories/weekly_counter.py::write": "keyword_at_callers",
}


def kept_or_unowned() -> set[str]:
    """Types no branch picks: the catalog says they point to no account, or keeps them."""
    from stoa.db import data_catalog

    return {
        name
        for name, entry in data_catalog.CATALOG.items()
        if entry.deletion is None or isinstance(entry.deletion.owner, data_catalog.Keep)
    }


# Types nothing writes any more whose stored rows may still be in the table:
# their branch keeps deleting them with the account. Each says what retired it.
NO_LONGER_WRITTEN: dict[str, str] = {
    # #518 retired the teacher assistance summary
    # (`GET /teachers/questions/{id}/assistance-summary`), its only writer.
    "teacher_assistance_summary_seed": "#518",
    # #518 retired the routes that made and reviewed AI exercise drafts. Drafts
    # already stored can still be set as an assignment (`sourceType: ai_draft`),
    # which only updates them (`ai_teacher_tools_service.mark_delivered`).
    "ai_teacher_draft": "#518",
    # #675 retired `POST /adaptive/students/{id}/memory/refresh`, the only writer.
    # The rows it stored are cleaned out once, but the deletion still reaches any.
    "learning_memory_snapshot": "#675",
    # #684 removed the payment expiry reminder's writers, which nothing called. The
    # read moved to `billing_fact_repo`; the notification sweep still takes any row.
    "payment_expiry_reminder": "#684",
}


# -- rows the branches pick -----------------------------------------------------------

ACCOUNT = "account-534"
OTHER = "someone-else-534"


def _row(key: Mapping[str, str], entity_type: str, **fields: Any) -> dict[str, Any]:
    return {**key, "entity_type": entity_type, **fields}


def deleted_by_branch() -> dict[str, tuple[str, dict[str, Any]]]:
    """`entity_type` -> (the branch that picks it, one such row of `ACCOUNT`'s).

    Each row is keyed and owned the way its writer keys and owns it - with the
    writer's own key function where there is one - since that is what the
    branches test.
    """
    from stoa.db.repositories import (
        account_invitation_repo,
        ai_teacher_tools_repo,
        allowance_repo,
        asked_knowledge_repo,
        attachment_repo,
        billing_fact_repo,
        capability_repo,
        identity_repo,
        notification_repo,
        parent_link_repo,
        practice_repo,
        review_repo,
        upload_code_repo,
        voice_question_consent_repo,
        voice_transcription_usage_repo,
        websocket_repo,
        weekly_counter,
    )
    from stoa.services import help_requests, teacher_support_allowance_service, usage_period
    from stoa.services.ask_question import _store as ask_store
    from stoa.services.learning_session import _store as conversation_store

    owner = {"owner_id": ACCOUNT, "student_id": ACCOUNT}
    conversation = conversation_store.conv_pk("conv-534")
    quiz = practice_repo.quiz_partition(ACCOUNT)
    activity = practice_repo.activity_partition(ACCOUNT)
    capability = ("teacher_identity_reviewer", "global")
    rows: dict[str, tuple[str, dict[str, Any]]] = {}

    def add(branch: str, row: dict[str, Any]) -> None:
        rows[row["entity_type"]] = (branch, row)

    # account_profile
    add("account_profile", _row(
        parent_link_repo.student_side_key(ACCOUNT, OTHER), "parent_student_link",
        student_id=ACCOUNT, parent_id=OTHER))
    add("account_profile", _row(
        {"PK": f"USER#{ACCOUNT}", "SK": f"{usage_period.RECORD_SK_PREFIX}2026-11-01#r1"},
        "usage_period_record", user_id=ACCOUNT))
    add("account_profile", _row(
        voice_question_consent_repo.state_key(ACCOUNT), "voice_question_consent",
        student_id=ACCOUNT, changed_by=OTHER))
    add("account_profile", _row(
        voice_question_consent_repo.change_key(ACCOUNT, "2026-11-01T00:00:00+00:00", "c1"),
        "voice_question_consent_change", student_id=ACCOUNT, changed_by=OTHER))
    add("account_profile", _row(
        voice_transcription_usage_repo.day_key(ACCOUNT, "2026-11-01"),
        "voice_transcription_day", student_id=ACCOUNT))
    add("account_profile", _row(
        allowance_repo._effect_key(ACCOUNT, "b" * 64), "allowance_effect",
        beneficiary_id=ACCOUNT, plan_id="plan-1"))
    add("account_profile", _row(
        allowance_repo._evidence_key(ACCOUNT, "c" * 64), "provider_usage_evidence",
        beneficiary_id=ACCOUNT, effect_id="b" * 64))
    add("account_profile", _row(
        {"PK": f"{weekly_counter.TOKENS.namespace}#{ACCOUNT}", "SK": "WEEK#2026-W45"},
        weekly_counter.TOKENS.entity_type, beneficiary_id=ACCOUNT))
    add("account_profile", _row(
        {"PK": "TEACHER_SUPPORT_CASE#case-digest", "SK": "ADMISSION"},
        "teacher_support_admission", beneficiary_id=ACCOUNT, parent_id=OTHER))
    add("account_profile", _row(
        {"PK": f"USER#{ACCOUNT}", "SK": teacher_support_allowance_service.ASSIGNED_ALLOWANCE_SK},
        "teacher_support_assigned_allowance", student_id=ACCOUNT, weekly_cases=3))
    # identity_cross_account
    add("identity_cross_account", _row(
        {"PK": "IDENTITY#issuer#subject", "SK": "BINDING"}, "identity_binding",
        user_id=ACCOUNT))
    add("identity_cross_account", _row(
        {"PK": f"USER#{ACCOUNT}", "SK": "IDENTITY#issuer#subject"}, "user_identity_inventory",
        user_id=ACCOUNT, binding_pk="IDENTITY#issuer#subject"))
    add("identity_cross_account", _row(
        {"PK": "PUBLIC_IDENTITY#digest", "SK": "COMMAND"}, "public_identity_command",
        user_id=ACCOUNT))
    add("identity_cross_account", _row(
        account_invitation_repo.invitation_key("token-digest"), "account_invitation",
        account_id=ACCOUNT))
    add("identity_cross_account", _row(
        identity_repo._sign_in_session_key(ACCOUNT, "jti-1"), "auth_sign_in_session"))
    # capability_scope
    add("capability_scope", _row(
        capability_repo._pointer_key(ACCOUNT, *capability), "capability_grant_current",
        user_id=ACCOUNT))
    add("capability_scope", _row(
        capability_repo._version_key(ACCOUNT, *capability, 1, "g1", 1),
        "capability_grant_revision", user_id=ACCOUNT))
    # attachments
    add("attachments", _row(attachment_repo.attachment_key("att-1"), "attachment", **owner))
    add("attachments", _row(
        attachment_repo.association_key("att-1", "conversation", "conv-534", "m1"),
        "attachment_association", **owner))
    add("attachments", _row({"PK": "UPLOAD#up-1", "SK": "META"}, "upload_intent", **owner))
    add("attachments", _row(
        upload_code_repo.code_key("code-1"), "upload_code", owner_id=ACCOUNT))
    # moderation: an image case is owned by its uploader (#139); its events by the case.
    add("moderation", _row(
        {"PK": "MODERATION#case-1", "SK": "SUMMARY"}, "moderation_case",
        case_id="case-1", surface="image_upload", student_id=ACCOUNT, privacy_generation=1))
    add("moderation", _row(
        {"PK": "MODERATION#case-1", "SK": "EVENT#e1"}, "moderation_event",
        case_id="case-1", student_id=ACCOUNT))
    # report_records / report_artifacts
    add("report_records", _row(
        {"PK": f"USER#{ACCOUNT}", "SK": "REPORT_EMAIL#op-1"}, "report_email_intent",
        owner_id=ACCOUNT))
    add("report_records", _row(
        {"PK": "REPORT#rep-1", "SK": "AUDIT#2026-11-01T00:00:00+00:00#e1"},
        "REPORT_AUDIT_EVENT", student_id=ACCOUNT))
    add("report_records", _row(
        {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "SUMMARY"}, "REPORT_RECOVERY_JOB",
        job_id="job-1", filters={"student_id": ACCOUNT}))
    add("report_records", _row(
        {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "TARGET#00000#t1"},
        "REPORT_RECOVERY_JOB_TARGET", job_id="job-1", student_id=ACCOUNT))
    add("report_records", _row(
        {"PK": "REPORT_RECOVERY_JOB#job-1", "SK": "AUDIT#2026-11-01T00:00:00+00:00#e1"},
        "REPORT_RECOVERY_JOB_AUDIT_EVENT", job_id="job-1", metadata={"student_id": ACCOUNT}))
    add("report_artifacts", _row(
        {"PK": f"USER#{ACCOUNT}", "SK": "REPORT_OBJECT#op-1#pdf"}, "report_object_intent",
        owner_id=ACCOUNT, version_id="v1"))
    # conversation_messages
    add("conversation_messages", _row(
        {"PK": conversation, "SK": "CONV"}, "conversation", **owner))
    add("conversation_messages", _row(
        {"PK": conversation, "SK": conversation_store.msg_sk("m1")}, "conversation_message",
        **owner))
    add("conversation_messages", _row(
        ask_store.message_command_key("conv-534", "idem-1"), "message_command", **owner))
    add("conversation_messages", _row(
        {"PK": conversation, "SK": "NOTE#n1"}, "conversation_teacher_note",
        teacher_id=OTHER, **owner))
    add("conversation_messages", _row(
        help_requests.key("conv-534"), "help_request", **owner))
    add("conversation_messages", _row(
        asked_knowledge_repo.record_key("conv-534", "m1"), "asked_knowledge_points", **owner))
    add("conversation_messages", _row(
        ask_store.chat_quota_operation_key(ACCOUNT, "cmd-1"), "chat_quota_operation",
        owner_id=ACCOUNT))
    add("conversation_messages", _row(
        {"PK": f"USAGE_LEDGER#{ACCOUNT}", "SK": "EVENT#ask#2026-11#k1"}, "usage_ledger_event",
        student_id=ACCOUNT))
    # practice_progress
    add("practice_progress", _row(
        {"PK": f"USAGE#{ACCOUNT}", "SK": "VOICE_QUOTA_OP#op-1"}, "rate_admission_operation",
        owner_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": f"USAGE#{ACCOUNT}", "SK": "VOICE#2026-11"}, "rate_counter"))
    add("practice_progress", _row(
        {"PK": f"PROGRESS#{ACCOUNT}", "SK": "LESSON#l1"}, "practice_progress",
        student_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": practice_repo.study_day_partition(ACCOUNT), "SK": "STUDY_DAY#2026-11-01"},
        "study_day", student_id=ACCOUNT, user_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": activity, "SK": "LIT_UNIT#u1"}, "lit_unit", student_id=ACCOUNT, user_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": activity, "SK": "LIT_LEDGER"}, "lit_ledger", student_id=ACCOUNT, user_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": quiz, "SK": "QUIZ_PAPER#q1"}, "practice_quiz_paper", student_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": quiz, "SK": "QUIZ_CREDENTIAL#c1"}, "practice_quiz_credential", student_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": quiz, "SK": "STAR_QUIZ_COOLDOWN#u1#q1"}, "practice_star_quiz_cooldown",
        student_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": quiz, "SK": "STAR_QUIZ_PASS#u1"}, "practice_star_quiz_pass", student_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": review_repo.card_partition(ACCOUNT), "SK": "CARD#ch1"}, "review_card",
        student_id=ACCOUNT, user_id=ACCOUNT))
    add("practice_progress", _row(
        practice_repo.attempt_rollup_key(ACCOUNT, "l1", "u1"), "practice_attempt_rollup",
        student_id=ACCOUNT, user_id=ACCOUNT, owner_id=ACCOUNT))
    add("practice_progress", _row(
        {"PK": f"ATTEMPTS#{ACCOUNT}", "SK": practice_repo.ATTEMPT_ROLLUP_STATE_SK},
        "practice_attempt_rollup_state", student_id=ACCOUNT, user_id=ACCOUNT, owner_id=ACCOUNT))
    # adaptive_assignment / learning_memory / ai_teacher_draft / curriculum_signal
    add("adaptive_assignment", _row(
        {"PK": "ASSIGNMENT#a1", "SK": "META"}, "learning_assignment", student_id=ACCOUNT))
    add("learning_memory", _row(
        {"PK": f"LEARNING_MEMORY#{ACCOUNT}", "SK": "SUBJECT#math#TOPIC#t1"},
        "learning_memory_snapshot", student_id=ACCOUNT))
    add("ai_teacher_draft", _row(
        {"PK": ai_teacher_tools_repo.draft_pk("d1"), "SK": "META"}, "ai_teacher_draft",
        student_id=ACCOUNT))
    add("curriculum_signal", _row(
        {"PK": f"CURRICULUM_SIGNAL_OWNER#{ACCOUNT}", "SK": "SIGNAL#s1"},
        "curriculum_signal_owner_manifest", signal_id="s1"))
    # notification_device_realtime
    add("notification_device_realtime", _row(
        {"PK": notification_repo.notification_pk("e1"), "SK": "META"}, "notification_event",
        owner_id=ACCOUNT))
    add("notification_device_realtime", _row(
        {"PK": notification_repo.preference_pk(ACCOUNT), "SK": "CURRENT"},
        "notification_preference", user_id=ACCOUNT, owner_id=ACCOUNT))
    add("notification_device_realtime", _row(
        {"PK": notification_repo.push_token_pk(ACCOUNT, "ref-1"), "SK": "TOKEN"},
        "notification_push_token", user_id=ACCOUNT, owner_id=ACCOUNT))
    add("notification_device_realtime", _row(
        {"PK": notification_repo.delivery_intent_pk(ACCOUNT),
         "SK": notification_repo.delivery_intent_sk("op-1")},
        "notification_delivery_intent", owner_id=ACCOUNT))
    add("notification_device_realtime", _row(
        # Keyed as `put_summary_seed` keyed it before #518.
        {"PK": "ASSISTANCE_SUMMARY#s1", "SK": "META"},
        "teacher_assistance_summary_seed", **owner))
    add("notification_device_realtime", _row(
        {"PK": billing_fact_repo.payment_expiry_reminder_pk(ACCOUNT),
         "SK": billing_fact_repo.payment_expiry_reminder_sk("a" * 64)},
        # Keyed as `put_payment_expiry_reminder` keyed it before #684.
        "payment_expiry_reminder", owner_id=ACCOUNT, parent_id=ACCOUNT))
    add("notification_device_realtime", _row(
        {"PK": websocket_repo.connection_pk("ws-1"), "SK": "META"}, "websocket_connection",
        user_id=ACCOUNT, owner_id=ACCOUNT))
    return rows


class _PurgeDone(dict[str, int]):
    status = "complete"


class _AnyClient:
    """Any external client call answers an empty success."""

    class exceptions:  # noqa: N801 - the boto3 client's attribute name
        class UserNotFoundException(Exception):  # noqa: N818 - Cognito's name
            pass

    def __getattr__(self, _name: str) -> Any:
        return lambda *_args, **_kwargs: {}


# Who writes the rows `picks_by_branch` stores: an account of its own, so its
# fenced write registers nothing under `ACCOUNT` that the catalog does not.
WRITER = "writer-590"


def picks_by_branch(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]
) -> dict[str, set[tuple[str, str]]]:
    """Run every branch over `ACCOUNT` with `rows` stored: the keys each one picked.

    The operations a branch hands its rows to are replaced by a recorder, so
    each branch reads what it would and changes nothing. The read is the
    registry path's: `ACCOUNT`'s derived partitions and the partitions
    registered under it. The rows are written by another account through the
    real `fenced` write, so what is registered under `ACCOUNT` is only what the
    data type catalog says the rows point to (#590): a row whose registration
    the catalog misses is a row its branch does not find.
    """
    from fakes.dynamodb import FakeTable
    from stoa import aws
    from stoa.aws import Kind
    from stoa.db import table as db_table
    from stoa.db.repositories import (
        account_deletion_repo,
        adaptive_learning_repo,
        ai_teacher_tools_repo,
        attachment_repo,
        curriculum_analytics_repo,
        moderation_repo,
        notification_repo,
        practice_repo,
        report_repo,
        websocket_repo,
    )
    from stoa.services import (
        account_deletion_service as service,
        ask_question,
        attachment_service,
        moderation_service,
    )

    table = FakeTable()
    table.seed_active_account(ACCOUNT)
    table.seed_active_account(WRITER)
    for row in rows:
        db_table.fenced(WRITER, [{"Put": {"Item": row}}], table=table)
    db_table.install(table)
    aws.install({Kind.S3: _AnyClient(), Kind.COGNITO: _AnyClient()})

    picked: dict[str, set[tuple[str, str]]] = {branch: set() for branch in service.BRANCH_HANDLERS}
    running = [""]

    def record(item: Mapping[str, Any], *_args: Any, **_kwargs: Any) -> dict[str, str]:
        picked[running[0]].add((str(item.get("PK")), str(item.get("SK"))))
        return {"status": "purged"}

    # The base branches hand their rows to a `mutate` of their own.
    run_base = service._run_base_branch
    monkeypatch.setattr(
        service, "_run_base_branch", lambda **kwargs: run_base(**{**kwargs, "mutate": record})
    )
    # The attachment branch purges the whole owner once it meets one of these.
    is_debt = service._is_attachment_debt

    def attachment_debt(item: Mapping[str, Any], owner_id: str) -> bool:
        if is_debt(item, owner_id):
            record(item)
            return True
        return False

    monkeypatch.setattr(service, "_is_attachment_debt", attachment_debt)
    for module, name in (
        (moderation_repo, "scrub_moderation_row"),
        (report_repo, "scrub_report_private_row"),
        (report_repo, "purge_report_object_intent"),
        (attachment_repo, "scrub_conversation_private_row"),
        (practice_repo, "scrub_practice_private_row"),
        (adaptive_learning_repo, "scrub_adaptive_private_row"),
        (ai_teacher_tools_repo, "scrub_ai_draft_private_row"),
        (curriculum_analytics_repo, "reconcile_curriculum_signal"),
        (notification_repo, "scrub_notification_private_row"),
        (websocket_repo, "revoke_account_connection"),
    ):
        monkeypatch.setattr(module, name, record)
    # What the branches do besides acting on a row: nothing, here.
    for module, name, answer in (
        (account_deletion_repo, "create_provider_revoke_debt", None),
        (account_deletion_repo, "close_unused_provider_revoke_debt", None),
        (attachment_service, "purge_student_attachments", _PurgeDone()),
        (attachment_service, "release_conversation_attachments", None),
        (ask_question, "cancel_for_account_deletion", None),
        (moderation_service, "delete_case_image", None),
    ):
        monkeypatch.setattr(module, name, lambda *_a, _answer=answer, **_k: _answer)

    command = {"user_id": ACCOUNT, "generation": 1, "command_id": "cmd-534", "branch_results": {}}
    with account_deletion_repo.registry_scope(ACCOUNT, table=table):
        for branch_id, handler in service.BRANCH_HANDLERS.items():
            running[0] = branch_id
            previous: dict[str, Any] = {}
            for _page in range(100):
                result = handler(command=command, previous=previous)
                if result.cursor is None:
                    break
                previous = {
                    "cursor": result.cursor,
                    "debt_counts": result.debt_counts,
                    "epoch": result.epoch,
                }
            else:
                raise AssertionError(f"{branch_id} kept paging")
    return picked


# -- tests --------------------------------------------------------------------------


def test_every_written_entity_type_is_deleted_by_a_branch_or_kept():
    found, _ = written_entity_types(ROOT)
    listed = deleted_by_branch().keys() | kept_or_unowned()
    new = {entity_type: sorted(found[entity_type]) for entity_type in sorted(found.keys() - listed)}
    assert not new, (
        "rows written with an entity_type no deletion branch is listed for: make a branch "
        "pick it and add a row of it to deleted_by_branch(), or say in the data type catalog "
        f"that it points to no account or why it is kept (Keep): {new}"
    )


def test_the_lists_name_only_entity_types_the_code_writes():
    found, _ = written_entity_types(ROOT)
    listed = deleted_by_branch().keys()
    stale = sorted(listed - found.keys() - NO_LONGER_WRITTEN.keys())
    assert not stale, (
        "no longer written anywhere in src/stoa: remove from the lists, or, if rows of it "
        f"may still be stored, keep its branch and list it in NO_LONGER_WRITTEN: {stale}"
    )


def test_a_type_no_longer_written_is_not_written_and_is_still_deleted():
    found, _ = written_entity_types(ROOT)
    written_again = {
        entity_type: sorted(found[entity_type])
        for entity_type in sorted(NO_LONGER_WRITTEN.keys() & found.keys())
    }
    assert not written_again, (
        f"written again: take it out of NO_LONGER_WRITTEN: {written_again}"
    )
    assert sorted(NO_LONGER_WRITTEN.keys() - deleted_by_branch().keys()) == [], (
        "rows that may still be stored need a branch that deletes them"
    )


def test_no_entity_type_is_both_deleted_and_kept():
    assert sorted(deleted_by_branch().keys() & kept_or_unowned()) == []


def test_every_unresolved_writer_is_reviewed():
    _, unresolved = written_entity_types(ROOT)
    assert sorted(unresolved - UNRESOLVED_WRITERS.keys()) == [], (
        "a writer whose entity_type the scan cannot read: say in UNRESOLVED_WRITERS what "
        "it writes, and list those types"
    )
    assert sorted(UNRESOLVED_WRITERS.keys() - unresolved) == [], "stale UNRESOLVED_WRITERS"


def test_each_deleted_entity_type_reaches_the_branch_it_is_listed_under(monkeypatch):
    listed = deleted_by_branch()
    picked = picks_by_branch(monkeypatch, [row for _, row in listed.values()])
    missed = {
        entity_type: {
            "listed": branch,
            "picked_by": sorted(b for b, keys in picked.items() if (row["PK"], row["SK"]) in keys),
        }
        for entity_type, (branch, row) in sorted(listed.items())
        if (row["PK"], row["SK"]) not in picked[branch]
    }
    assert not missed, missed


def test_the_branch_run_picks_nothing_of_another_account(monkeypatch):
    """The recorder records picks, not reads: the same rows of another account reach none.

    Every row of `deleted_by_branch()` with `ACCOUNT` swapped for a third
    account, wherever it appears; the partitions stay registered under
    `ACCOUNT`, so the branches still read them.
    """
    third = "third-account-534"
    others = [
        json.loads(json.dumps(row).replace(ACCOUNT, third))
        for _, row in deleted_by_branch().values()
    ]
    picked = picks_by_branch(monkeypatch, others)
    reached = {(row["PK"], row["SK"]) for row in others} & set().union(*picked.values())
    assert not reached, sorted(reached)


def test_the_scan_sees_a_new_entity_type(tmp_path):
    source = tmp_path / "src" / "stoa"
    (source / "db").mkdir(parents=True)
    (source / "db" / "kinds.py").write_text('SHARED = "shared_row"\n', encoding="utf-8")
    (source / "new_repo.py").write_text(
        "\n".join(
            [
                "from stoa.db import kinds",
                'LOCAL = "constant_row"',
                "",
                "def put_one(table, owner):",
                '    table.put_item(Item={"PK": owner, "SK": "A", "entity_type": "literal_row"})',
                '    table.put_item(Item={"PK": owner, "SK": "B", "entity_type": LOCAL})',
                '    table.put_item(Item={"PK": owner, "SK": "C", "entity_type": kinds.SHARED})',
                "",
                "def count(table, owner):",
                "    table.update_item(",
                '        Key={"PK": owner, "SK": "D"},',
                '        UpdateExpression="SET entity_type = :entity ADD hits :one",',
                '        ExpressionAttributeValues={":entity": "updated_row", ":one": 1},',
                "    )",
                "",
                "def only_reads(table, owner):",
                "    table.update_item(",
                '        Key={"PK": owner, "SK": "E"},',
                '        UpdateExpression="SET hits = :one",',
                '        ConditionExpression="entity_type = :entity",',
                '        ExpressionAttributeValues={":entity": "read_row", ":one": 1},',
                "    )",
                "",
                "def tombstone(table, item):",
                '    table.put_item(Item={**item, "entity_type": f"{item[\'kind\']}_gone"})',
                "",
            ]
        ),
        encoding="utf-8",
    )
    found, unresolved = written_entity_types(tmp_path)
    assert set(found) == {"literal_row", "constant_row", "shared_row", "updated_row"}
    assert unresolved == {"src/stoa/new_repo.py::tombstone"}


# -- 4. the catalog's deletion is the branch's ------------------------------------------


def _identity_evidence_fields() -> frozenset[str]:
    """The fields `terminalize_identity_row` writes in place of an identity or grant."""
    from stoa.db.repositories import account_deletion_repo

    written: list[dict[str, Any]] = []

    class _Recorder:
        def replace_with_deletion_tombstone(self, _item, evidence, *_args) -> None:
            written.append(evidence)

    account_deletion_repo.terminalize_identity_row(
        {"PK": "IDENTITY#i#s", "SK": "BINDING", "user_id": ACCOUNT, "version": 1},
        user_id=ACCOUNT, generation=1, now_iso="2026-11-25T00:00:00+00:00", table=_Recorder(),
    )
    return frozenset(written[0])


def family_actions() -> dict[str, Any]:
    """Each branch's action on the rows it picks: "delete", or its tombstone's allowlist."""
    from stoa.db.repositories import (
        account_deletion_repo,
        adaptive_learning_repo,
        ai_teacher_tools_repo,
        attachment_repo,
        moderation_repo,
        notification_repo,
        practice_repo,
        report_repo,
    )

    return {
        "account_profile": "delete",
        "identity_cross_account": "delete",
        "capability_scope": _identity_evidence_fields(),
        "question_ocr_session": account_deletion_repo.QUESTION_TOMBSTONE_ALLOWLIST,
        "attachments": "delete",
        "moderation": moderation_repo.MODERATION_TOMBSTONE_ALLOWLIST,
        "report_records": report_repo.REPORT_TOMBSTONE_ALLOWLIST,
        "report_artifacts": report_repo.REPORT_TOMBSTONE_ALLOWLIST,
        "conversation_messages": attachment_repo.CONVERSATION_TOMBSTONE_ALLOWLIST,
        "practice_progress": practice_repo.PRACTICE_TOMBSTONE_ALLOWLIST,
        "adaptive_assignment": adaptive_learning_repo.ADAPTIVE_TOMBSTONE_ALLOWLIST,
        "learning_memory": adaptive_learning_repo.ADAPTIVE_TOMBSTONE_ALLOWLIST,
        "ai_teacher_draft": ai_teacher_tools_repo.AI_DRAFT_TOMBSTONE_ALLOWLIST,
        "curriculum_signal": "delete",
        "notification_device_realtime": notification_repo.NOTIFICATION_TOMBSTONE_ALLOWLIST,
    }


# Within a branch, rows handled unlike the rest of it.
BRANCH_EXCEPTIONS: dict[str, str] = {
    # `terminalize_identity_row`, after the sign-in provider's user is revoked.
    "identity_binding": "capability_scope",
    "user_identity_inventory": "capability_scope",
    "public_identity_command": "capability_scope",
    # `revoke_account_connection` deletes the connection.
    "websocket_connection": "account_profile",
}

# Kinds the branches handle that `deleted_by_branch()` does not list: written with
# no `entity_type`, or legacy kinds nothing writes. The branch whose action they get.
HANDLED_UNLISTED: dict[str, str] = {
    # The profile's own deletion tombstone, which has the question allowlist.
    "user_profile": "question_ocr_session",
    "question": "question_ocr_session",
    "teacher_escalation_intent": "question_ocr_session",
    "attachment_storage_usage": "attachments",
    "report_summary": "report_records",
    "usage_counter": "practice_progress",
    "practice_attempt": "practice_progress",
    **{
        f"legacy_untyped_{suffix}": "practice_progress"
        for suffix in (
            "progress", "review", "activity", "quiz", "usage_ledger",
            "practice", "practice_attempt", "practice_progress",
        )
    },
}


def _action(deletion: Any) -> Any:
    from stoa.db import data_catalog

    owner = deletion.owner
    if isinstance(owner, data_catalog.Delete):
        return "delete"
    if isinstance(owner, data_catalog.Tombstone):
        return owner.keeps
    return owner


def test_the_catalog_says_what_the_branch_that_picks_a_type_does():
    from stoa.db import data_catalog
    from stoa.db.repositories import account_deletion_repo

    actions = family_actions()
    expected = {
        name: actions[BRANCH_EXCEPTIONS.get(name, branch)]
        for name, (branch, _) in deleted_by_branch().items()
    }
    expected.update({name: actions[branch] for name, branch in HANDLED_UNLISTED.items()})
    # A teacher session is tombstoned with the session allowlist, whichever side is deleted.
    expected["teacher_session"] = account_deletion_repo.SESSION_TOMBSTONE_ALLOWLIST
    entries = {entry.name: entry for entry in (*data_catalog.CATALOG.values(), *data_catalog.UNTYPED)}
    wrong = {
        name: {"branch": want if isinstance(want, str) else sorted(want),
               "catalog": _action(entries[name].deletion)}
        for name, want in sorted(expected.items())
        if _action(entries[name].deletion) != want
    }
    assert not wrong, wrong


def test_every_type_the_deletion_handles_is_checked_against_its_branch():
    from stoa.db import data_catalog

    handled = {
        entry.name
        for entry in (*data_catalog.CATALOG.values(), *data_catalog.UNTYPED)
        if entry.deletion is not None and not isinstance(entry.deletion.owner, data_catalog.Keep)
    }
    checked = deleted_by_branch().keys() | HANDLED_UNLISTED.keys() | {"teacher_session"}
    assert sorted(handled - checked) == [], "add the type to deleted_by_branch() or HANDLED_UNLISTED"
    assert sorted(checked - handled) == [], "the catalog keeps it, or it points to no account"
