"""The data type catalog is complete, and says what the old rules said (#587).

`stoa.db.data_catalog` lists every kind of row and the accounts it points to.
Account deletion reads it since #588; the owner registry and the sweep switch
over in #589-#590. Three gates hold it in place:

1. **Closed world.** Every `entity_type` the code writes
   (`entity_type_scan.written_entity_types`) has an entry, and every entry is a
   type the code writes - or one it no longer writes but whose rows the
   deletion still reaches (`no_longer_written`, matching the branch gate's
   `NO_LONGER_WRITTEN`), or a `legacy` type the deletion reads and nothing
   here writes.
2. **Writer fields.** Every attribute a writer puts beside an `entity_type`
   that looks like an account id (`looks_like_account`) is declared in that
   type's entry, as a pointer or as a reasoned `NotPointer`. A writer whose
   fields the scan cannot see (a spread of a parameter) is listed in
   `FIELDS_READ_BY_HAND` with where the fields come from; its entry was
   declared by reading the code.
3. **Parity.** For every entry, synthetic rows put an id in each declared
   pointer and in each field the old rules read on any row; and every row the
   deletion branch gate builds (`deleted_by_branch`) is compared too. The old
   answer (`compare_data_catalog.old_rule`: `mentioned_accounts`, which
   registration still reads, and the deletion rules as they stood before #588,
   frozen in that script) and the catalog's
   (`mentions`) must agree, except for the intended differences in
   `compare_data_catalog.INTENDED` - each one a decision in #586 - and the
   role changes in `compare_data_catalog.ROLE_CHANGES`.

A new kind of row fails 1 until it has an entry; a new account field on a
writer fails 2 until it is declared or reasoned away.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

import compare_data_catalog as compare
from entity_type_scan import ROOT, written_entity_types, written_fields
from stoa.db import data_catalog
from stoa.db.data_catalog import (
    CATALOG,
    OWNER,
    REFERENCE,
    UNTYPED,
    DataType,
    Field,
    Ids,
    KeyId,
    ScopeId,
    Summaries,
)
from stoa.db.repositories import notification_repo

PROBE = "probe-587"
OTHER = "other-587"


# -- 1. closed world ------------------------------------------------------------------------


def _writer_modules(writers: set[str]) -> set[str]:
    return {
        writer.split("::")[0]
        .removeprefix("src/")
        .removesuffix(".py")
        .removesuffix("/__init__")
        .replace("/", ".")
        for writer in writers
    }


def test_every_written_entity_type_has_a_catalog_entry():
    found, _ = written_entity_types(ROOT)
    missing = {name: sorted(found[name]) for name in sorted(found.keys() - CATALOG.keys())}
    assert not missing, (
        "rows written with an entity_type the data type catalog does not list: add an entry "
        f"to stoa.db.data_catalog (its account pointers, or none) - {missing}"
    )
    assert len(found) >= 138


def test_the_catalog_lists_only_types_the_code_writes_or_the_deletion_still_reaches():
    from test_account_deletion_branch_coverage import NO_LONGER_WRITTEN

    found, _ = written_entity_types(ROOT)
    stale = sorted(
        name
        for name, entry in CATALOG.items()
        if entry.lifecycle == "written" and name not in found
    )
    assert not stale, f"listed as written, but nothing in src/stoa writes it: {stale}"
    written_again = sorted(
        name for name, entry in CATALOG.items() if entry.lifecycle != "written" and name in found
    )
    assert not written_again, f"written again: mark it `written`: {written_again}"
    retired = {name for name, entry in CATALOG.items() if entry.lifecycle == "no_longer_written"}
    assert retired == set(NO_LONGER_WRITTEN), (
        "`no_longer_written` entries and the branch gate's NO_LONGER_WRITTEN must agree"
    )


def test_a_legacy_type_is_one_the_deletion_still_reads():
    deletion = "".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "src/stoa/db/repositories/account_deletion_repo.py",
            "src/stoa/services/account_deletion_service.py",
        )
    )
    unread = sorted(
        name
        for name, entry in CATALOG.items()
        if entry.lifecycle == "legacy" and f'"{name}"' not in deletion
    )
    assert not unread, f"no writer and the deletion no longer reads it: remove it: {unread}"


def test_each_entry_names_the_module_that_writes_it():
    found, _ = written_entity_types(ROOT)
    wrong = {
        name: (entry.module, sorted(_writer_modules(found[name])))
        for name, entry in CATALOG.items()
        if name in found and entry.module not in _writer_modules(found[name])
    }
    assert not wrong, wrong


def test_untyped_kinds_are_recognized_by_key_and_never_shadow_a_type():
    assert not {entry.name for entry in UNTYPED} & CATALOG.keys()
    assert all(entry.untyped_key is not None for entry in UNTYPED)
    assert all(entry.untyped_key is None for entry in CATALOG.values())
    # A typed row is never matched by its key.
    row = {"PK": "USER#a", "SK": "PROFILE", "entity_type": "somebody_elses_type"}
    assert data_catalog.data_type_of(row) is None
    assert data_catalog.data_type_of({"PK": "USER#a", "SK": "PROFILE"}).name == "user_profile"
    # A row tagged with an untyped kind's own name is that kind, if its key agrees.
    tagged = {"PK": "USER#a", "SK": "PROFILE", "entity_type": "user_profile"}
    assert data_catalog.data_type_of(tagged).name == "user_profile"
    assert data_catalog.data_type_of({**tagged, "SK": "OTHER"}) is None


def test_every_deletion_slot_is_still_empty():
    """Candidate I (see #586) fills `deletion`; until then nothing may read one."""
    assert all(entry.deletion is None for entry in (*CATALOG.values(), *UNTYPED))


# -- 2. writer fields -----------------------------------------------------------------------

# Attribute names that hold an account id, or may: every one a writer writes
# must be declared by its type, as a pointer or a reasoned `NotPointer`.
ACCOUNT_FIELDS = frozenset(
    {
        "owner_id",
        "student_id",
        "user_id",
        "child_id",
        "child_user_id",
        "target_user_id",
        "parent_id",
        "teacher_id",
        "dispatched_teacher_id",
        "beneficiary_id",
        "beneficiary_ids",
        "account_id",
        "actor",
        "actor_id",
        "recipient_id",
        "reporter_id",
        "reviewer_id",
        "grantor_id",
        "registry_account",
        "deletion_user_id",
        "scope",
        "children",
        "child_summaries",
        "student_summaries",
        "filters",
    }
)
ACCOUNT_SUFFIXES = (
    "_by",
    "_user_id",
    "_teacher_id",
    "_teacher_ids",
    "_student_id",
    "_parent_id",
    "_admin_id",
)


def looks_like_account(attribute: str) -> bool:
    name = attribute.removeprefix("metadata.")
    return name in ACCOUNT_FIELDS or name.endswith(ACCOUNT_SUFFIXES)


# Types with a writer whose fields the scan cannot see, and where they come
# from; each entry was declared by reading that code.
FIELDS_READ_BY_HAND: Mapping[str, str] = {
    # report_repo writers take a dict from their service.
    "REPORT_AUDIT_EVENT": "report_recovery_service._write_report_audit: parent/student_id, actor",
    "REPORT_RECOVERY_JOB": "report_recovery_job_service: created_by, filters{parent/student_id}",
    "REPORT_RECOVERY_JOB_AUDIT_EVENT": "report_recovery_job_service._audit: actor, metadata{...}",
    "REPORT_RECOVERY_JOB_TARGET": "report_recovery_job_service: parent_id, student_id",
    "AUDIT_RETENTION_EVENT": "no caller (KEPT no_caller)",
    "AUDIT_RETENTION_IMMUTABLE_MANIFEST": "no caller (KEPT no_caller)",
    "LEGAL_HOLD_AUDIT_EVENT": "no caller (KEPT no_caller)",
    "LEGAL_HOLD_METADATA": "no caller (KEPT no_caller)",
    "LEGAL_HOLD_REVIEW_METADATA": "no caller (KEPT no_caller)",
    "REPORT_ARTIFACT_EDIT_DRAFT": "no caller (KEPT no_caller)",
    "REPORT_ARTIFACT_ROLLBACK_PREVIEW": "no caller (KEPT no_caller)",
    "REPORT_EDIT_DRAFT": "no caller (KEPT no_caller)",
    "RETENTION_APPROVAL_AUDIT_EVENT": "no caller (KEPT no_caller)",
    "RETENTION_APPROVAL_METADATA": "no caller (KEPT no_caller)",
    "SUPPORT_CRM_MESSAGE_EVENT": "no caller (KEPT no_caller)",
    "SUPPORT_CRM_MESSAGE_FEED": "no caller (KEPT no_caller)",
    "SUPPORT_HANDOFF_AUDIT_EVENT": "no caller (KEPT no_caller)",
    "SUPPORT_HANDOFF_DELIVERY": "no caller (KEPT no_caller)",
    "SUPPORT_HANDOFF_DELIVERY_AUDIT_EVENT": "no caller (KEPT no_caller)",
    "SUPPORT_HANDOFF_DELIVERY_FEED": "no caller (KEPT no_caller)",
    # Everything else.
    "account_deletion_command": "account_deletion_repo: the command dict carries user_id",
    "account_invitation": "account_invitation_service: account_id, invited_by",
    "authorization_probe_aggregate": "security_audit_repo.project_audit_event: actor fingerprints",
    "capability_grant_revision": "capability_repo: a legacy revision copied as it was stored",
    "curriculum_analytics_signal": "curriculum_analytics_service: metadata.studentHash, a digest",
    "curriculum_audit_event": "curriculum_ops_service: authored-content audit, operator fields",
    "curriculum_migration_evidence": "curriculum_ops_service: migration evidence, operator fields",
    "curriculum_pointer": "curriculum_ops_repo: manifest, version, updated_by",
    "curriculum_publish_manifest": "curriculum_ops_service: authored-content manifest",
    "curriculum_version": "curriculum_ops_service: authored-content version",
    "learning_assignment": "adaptive_learning_service: student_id, created_by; repo adds owner_id",
    "learning_memory_snapshot": "adaptive_learning_service: student_id; repo stamps owner_id",
    "moderation_event": "moderation_service._event: actor_id, student_id",
    "payment_expiry_reminder": "notification_service: parent_id; repo stamps owner_id",
    "practice_quiz_paper": "practice_repo: the quiz scope's lesson/unit ids",
    "privileged_identity_command": "privileged_identity_service: target_id (a digest), approved_by",
    "provider_usage_evidence": "allowance_repo: cache token counts",
    "security_audit_event": "security_audit_repo.project_audit_event: actor fingerprints",
    "subscription_billing": "subscription_service: the stored billing row, re-put",
    "subscription_billing_event": "subscription_service: parent_id, provider fields",
    "teacher_activation_command": "teacher_application_service: user_id, verified_email",
    "teacher_activation_invitation": "teacher_application_service: application ids",
    "teacher_application_review": "teacher_application_service: reviewer_id",
    "teacher_application_version": "teacher_application_service: the applicant's answers",
    "upload_code": "upload_code_service: owner_id",
}


def _declared(entry: DataType) -> set[str]:
    attributes = {pointer.attribute for pointer in entry.accounts}
    return attributes | {item.attribute for item in entry.not_pointers}


def test_every_account_field_a_writer_writes_is_declared():
    fields = written_fields(ROOT)
    undeclared = {
        name: sorted(
            attribute
            for attribute in written.fields
            if looks_like_account(attribute) and attribute not in _declared(CATALOG[name])
        )
        for name, written in sorted(fields.items())
    }
    undeclared = {name: found for name, found in undeclared.items() if found}
    assert not undeclared, (
        "writers write these account-looking attributes, which their catalog entry neither "
        "declares as a pointer nor lists as a NotPointer with its reason: "
        f"{json.dumps(undeclared, indent=1)}"
    )


def test_every_writer_the_scan_cannot_read_is_read_by_hand():
    fields = written_fields(ROOT)
    opaque = {name for name, written in fields.items() if written.opaque}
    assert sorted(opaque - FIELDS_READ_BY_HAND.keys()) == [], (
        "a writer spreads a dict the scan cannot follow: read its fields, declare them in the "
        "catalog entry, and say in FIELDS_READ_BY_HAND where they come from"
    )
    assert sorted(FIELDS_READ_BY_HAND.keys() - opaque) == [], "stale FIELDS_READ_BY_HAND"


def test_a_field_is_a_pointer_or_not_never_both():
    both = {
        name: sorted(
            {pointer.attribute for pointer in entry.accounts}
            & {item.attribute for item in entry.not_pointers}
        )
        for name, entry in CATALOG.items()
    }
    assert not {name: found for name, found in both.items() if found}
    assert all(item.reason.strip() for entry in CATALOG.values() for item in entry.not_pointers)


def test_nothing_writes_target_user_id():
    """`target_user_id` leaves the rules (#586 decision 4) because no writer sets it."""
    import subprocess

    hits = subprocess.run(
        ["git", "grep", "-n", "target_user_id", "--", "src/stoa"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    readers = {"src/stoa/db/repositories/account_deletion_repo.py"}
    assert {line.split(":", 1)[0] for line in hits} <= readers, hits
    assert not any("target_user_id" in written.fields for written in written_fields(ROOT).values())


def test_the_scan_reads_the_fields_beside_an_entity_type(tmp_path):
    source = tmp_path / "src" / "stoa"
    source.mkdir(parents=True)
    (source / "repo.py").write_text(
        "\n".join(
            [
                "def put(table, owner, extra):",
                "    base = {'student_id': owner}",
                "    item = {'PK': owner, 'SK': 'A', 'entity_type': 'kind_a', **base,",
                "            'metadata': {'parent_id': owner}}",
                "    item['teacher_id'] = owner",
                "    table.put_item(Item=item)",
                "    table.put_item(Item={'entity_type': 'kind_b', **extra})",
                "",
                "def count(table, owner):",
                "    table.update_item(",
                "        Key={'PK': owner, 'SK': 'C'},",
                "        UpdateExpression='SET entity_type = :e, #o = :o ADD hits :one',",
                "        ExpressionAttributeNames={'#o': 'owner_id'},",
                "        ExpressionAttributeValues={':e': 'kind_c', ':o': owner, ':one': 1},",
                "    )",
                "",
            ]
        ),
        encoding="utf-8",
    )
    fields = written_fields(tmp_path)
    assert {"PK", "SK", "student_id", "metadata", "metadata.parent_id", "teacher_id"} <= fields[
        "kind_a"
    ].fields
    assert fields["kind_b"].opaque == {"src/stoa/repo.py::put": ["extra"]}
    assert fields["kind_c"].fields == {"owner_id", "hits"}


# -- the rule functions ------------------------------------------------------------------------


def test_ids_are_exact_and_never_hold_a_key_separator():
    row = {"PK": "CONV#c", "SK": "CONV", "entity_type": "conversation"}
    assert data_catalog.mentions({**row, "student_id": " padded "}) == {" padded ": OWNER}
    for value in ("a#b", "operator:agent_mcp", "a/b", "", "   ", 7, None):
        assert data_catalog.mentions({**row, "student_id": value}) == {}
    with pytest.raises(ValueError):
        data_catalog.names(row, "operator:agent_mcp")
    assert data_catalog.names({**row, "student_id": "s"}, "s")
    assert not data_catalog.names({**row, "student_id": "s"}, " s")


def test_owner_wins_over_reference():
    row = {
        "PK": "CONV#c",
        "SK": "REQUEST",
        "entity_type": "help_request",
        "student_id": "s",
        "teacher_id": "s",
        "previous_dispatch_teacher_ids": ["t1", "t2"],
    }
    assert data_catalog.mentions(row) == {"s": OWNER, "t1": REFERENCE, "t2": REFERENCE}


def test_each_pointer_shape_reads_its_ids():
    profile = {
        "PK": "USER#p",
        "SK": "PROFILE",
        "user_id": "p",
        "children": {"c1": {"user_id": "c2"}},
        "child_summaries": [{"student_id": "c3"}, {"child_id": "c4"}, "not-an-entry"],
    }
    assert data_catalog.mentions(profile) == {
        "p": OWNER,
        "c1": REFERENCE,
        "c2": REFERENCE,
        "c3": REFERENCE,
        "c4": REFERENCE,
    }
    grant = {"PK": "CAP#g", "SK": "V", "entity_type": "capability_grant_current", "user_id": "a"}
    assert data_catalog.mentions({**grant, "scope": "student:s"}) == {"a": OWNER, "s": OWNER}
    assert data_catalog.mentions({**grant, "scope": "student/s"}) == {"a": OWNER, "s": OWNER}
    assert data_catalog.mentions({**grant, "scope": "s"}) == {"a": OWNER}
    assert data_catalog.mentions({**grant, "scope": "global"}) == {"a": OWNER}
    sign_in = {"PK": "USER#u", "SK": "SIGNIN#jti", "entity_type": "auth_sign_in_session"}
    assert data_catalog.mentions(sign_in) == {"u": OWNER}
    link = {"PK": "PARENT#p", "SK": "CHILD#s", "entity_type": "parent_student_link"}
    assert data_catalog.mentions(link) == {"s": OWNER}
    event = {
        "PK": "NOTIFICATION#e",
        "SK": "META",
        "entity_type": "notification_event",
        "owner_id": "o",
        "metadata": {"student_id": "s", "teacher_id": "t", "filters": {"student_id": "x"}},
    }
    assert data_catalog.mentions(event) == {"o": OWNER, "s": OWNER, "t": REFERENCE}
    job = {
        "PK": "REPORT_RECOVERY_JOB#j",
        "SK": "AUDIT#1#e",
        "entity_type": "REPORT_RECOVERY_JOB_AUDIT_EVENT",
        "metadata": {"filters": {"parent_id": "p"}, "result_filters": ["ignored"]},
    }
    assert data_catalog.mentions(job) == {"p": OWNER}


def test_an_unknown_row_names_nobody_unless_asked_strictly():
    row = {"PK": "SOMETHING#x", "SK": "NEW", "entity_type": "brand_new_kind", "owner_id": "o"}
    assert data_catalog.mentions(row) == {}
    with pytest.raises(data_catalog.UnknownDataType):
        data_catalog.mentions_strict(row)
    untyped = {"PK": "NOBODY_KNOWS#x", "SK": "ROW", "owner_id": "o"}
    with pytest.raises(data_catalog.UnknownDataType):
        data_catalog.mentions_strict(untyped)
    tombstone = {
        "PK": "QUESTION#q",
        "SK": "META",
        "entity_type": "question_deletion_tombstone",
        "status": "deleted",
    }
    assert data_catalog.data_type_of(tombstone) is data_catalog.DELETION_TOMBSTONES
    assert data_catalog.mentions_strict(tombstone) == {}


# -- 3. parity ---------------------------------------------------------------------------------

# A key of each kind as its writer builds it, where today's rules read the key
# (a practice partition, a report family, a link SK). `{a}` is the account the
# key names. Any other entry gets a neutral key no rule reads.
SAMPLE_KEYS: Mapping[str, tuple[str, str]] = {
    "auth_sign_in_session": ("USER#{a}", "SIGNIN#jti"),
    "parent_student_link": ("PARENT#{o}", "CHILD#{a}"),
    "rate_admission_operation": ("USAGE#{a}", "VOICE_QUOTA_OP#op"),
    "rate_counter": ("USAGE#{a}", "VOICE#2026-11"),
    "chat_quota_operation": ("USAGE#{a}", "CHAT_QUOTA_OP#c"),
    "usage_ledger_event": ("USAGE_LEDGER#{a}", "EVENT#ask#2026-11#k"),
    "practice_progress": ("PROGRESS#{a}", "LESSON#l"),
    "study_day": ("ACTIVITY#{a}", "STUDY_DAY#2026-11-01"),
    "lit_unit": ("ACTIVITY#{a}", "LIT_UNIT#u"),
    "lit_ledger": ("ACTIVITY#{a}", "LIT_LEDGER"),
    "practice_quiz_paper": ("QUIZ#{a}", "QUIZ_PAPER#q"),
    "practice_quiz_credential": ("QUIZ#{a}", "QUIZ_CREDENTIAL#c"),
    "practice_star_quiz_cooldown": ("QUIZ#{a}", "STAR_QUIZ_COOLDOWN#u#q"),
    "practice_star_quiz_pass": ("QUIZ#{a}", "STAR_QUIZ_PASS#u"),
    "review_card": ("REVIEW#{a}", "CARD#c"),
    "learning_memory_snapshot": ("LEARNING_MEMORY#{a}", "SUBJECT#math#TOPIC#t"),
    "curriculum_signal_owner_manifest": ("CURRICULUM_SIGNAL_OWNER#{a}", "SIGNAL#s"),
    "conversation": ("CONV#c", "CONV"),
    "conversation_message": ("CONV#c", "MSG#m"),
    "conversation_teacher_note": ("CONV#c", "NOTE#n"),
    "message_command": ("CONV#c", "MESSAGE_COMMAND#i"),
    "help_request": ("CONV#c", "HELP_REQUEST"),
    "asked_knowledge_points": ("CONV#c", "KNOWLEDGE#m"),
    "attachment_association": ("ATTACHMENT#t", "REF#CONVERSATION#c#MESSAGE#m"),
    "REPORT_AUDIT_EVENT": ("REPORT#r", "AUDIT#2026-11-01#e"),
    "REPORT_RECOVERY_JOB": ("REPORT_RECOVERY_JOB#j", "SUMMARY"),
    "REPORT_RECOVERY_JOB_AUDIT_EVENT": ("REPORT_RECOVERY_JOB#j", "AUDIT#2026-11-01#e"),
    "REPORT_RECOVERY_JOB_TARGET": ("REPORT_RECOVERY_JOB#j", "TARGET#00000#t"),
    "report_email_intent": ("USER#{a}", "REPORT_EMAIL#op"),
    "report_object_intent": ("USER#{a}", "REPORT_OBJECT#op#pdf"),
    "user_profile": ("USER#{a}", "PROFILE"),
    "practice_attempt": ("ATTEMPTS#{a}", "ATTEMPT#x"),
    "usage_counter": ("USAGE#{a}", "QUESTION#2026-11-01"),
    "attachment_storage_usage": ("STORAGE#{a}", "USAGE"),
    "report_summary": ("REPORT#r", "SUMMARY"),
    "legacy_untyped_progress": ("PROGRESS#{a}", "TOPIC#t"),
    "legacy_untyped_review": ("REVIEW#{a}", "CARD#c"),
    "legacy_untyped_activity": ("ACTIVITY#{a}", "DAY#2026-11-01"),
    "legacy_untyped_quiz": ("QUIZ#{a}", "QUIZ#q"),
    "legacy_untyped_usage_ledger": ("USAGE_LEDGER#{a}", "EVENT#e"),
    "legacy_untyped_practice": ("PRACTICE#p", "META"),
    "legacy_untyped_practice_attempt": ("PRACTICE_ATTEMPT#p", "META"),
    "legacy_untyped_practice_progress": ("PRACTICE_PROGRESS#p", "META"),
}

KEY_ACCOUNT = "keyed-587"


def _base(entry: DataType) -> dict[str, Any]:
    pk, sk = SAMPLE_KEYS.get(entry.name, (f"PARITY#{entry.name}", "ROW"))
    row: dict[str, Any] = {
        "PK": pk.format(a=KEY_ACCOUNT, o=OTHER),
        "SK": sk.format(a=KEY_ACCOUNT, o=OTHER),
    }
    if entry.untyped_key is None:
        row["entity_type"] = (
            entry.name if not entry.name.startswith("*") else "question_deletion_tombstone"
        )
    return row


def _set(row: dict[str, Any], path: str, value: Any) -> None:
    *parents, last = path.split(".")
    holder = row
    for name in parents:
        holder = holder.setdefault(name, {})
    holder[last] = value


def _probe(entry: DataType, label: str, **changes: Any) -> tuple[str, dict[str, Any]]:
    row = _base(entry)
    for path, value in changes.items():
        _set(row, path.replace("__", "."), value)
    return label, row


def _pointer_probes(entry: DataType) -> list[tuple[str, dict[str, Any]]]:
    """Rows of `entry`'s kind, each with `PROBE` in one of its declared pointers."""
    rows: list[tuple[str, dict[str, Any]]] = []
    for pointer in entry.accounts:
        match pointer:
            case Field(path=path):
                rows.append(_probe(entry, path, **{path.replace(".", "__"): PROBE}))
            case Ids(path=path):
                rows.append(_probe(entry, path, **{path: [OTHER, PROBE]}))
            case Summaries(path=path):
                rows.append(_probe(entry, f"{path}{{}}", **{path: {PROBE: {"user_id": OTHER}}}))
                rows.append(_probe(entry, f"{path}[]", **{path: [{"student_id": PROBE}]}))
            case KeyId(key=key, prefix=prefix):
                rows.append(_probe(entry, key, **{key: f"{prefix}{PROBE}"}))
            case ScopeId(prefixes=prefixes):
                for prefix in prefixes:
                    rows.append(_probe(entry, f"scope {prefix}", scope=f"{prefix}{PROBE}"))
    return rows


def _rule_probes(entry: DataType) -> list[tuple[str, dict[str, Any]]]:
    """Rows of `entry`'s kind, each with `PROBE` in one place today's rules read."""
    rows: list[tuple[str, dict[str, Any]]] = []

    def probe(label: str, **changes: Any) -> None:
        rows.append(_probe(entry, label, **changes))

    # Read on any row, whatever its kind (`_targets_user`).
    for field in sorted(compare.GENERIC_FALLBACKS):
        probe(field, **{field: PROBE})
    if entry.name not in SAMPLE_KEYS:  # a kind whose SK a rule reads keeps its own
        probe("SK CHILD#", SK=f"CHILD#{PROBE}")
        probe("SK PARENT#", SK=f"PARENT#{PROBE}")
    for field in ("children", "child_summaries", "student_summaries"):
        probe(f"{field}{{}}", **{field: {PROBE: {}}})
        probe(f"{field}[]", **{field: [{"child_id": PROBE}]})
    probe("scope student:", scope=f"student:{PROBE}")
    probe("scope student/", scope=f"student/{PROBE}")
    probe("bare scope", scope=PROBE)
    # Read on some kinds only.
    scalar, collection, metadata = (
        compare.OLD_CROSS_ACCOUNT_REFERENCES.get(
            entry.name, (frozenset(), frozenset(), frozenset())
        )
    )
    for field in sorted(scalar):
        probe(field, **{field: PROBE})
    for field in sorted(collection):
        probe(field, **{field: [PROBE]})
    inside = set(metadata)
    if entry.name in notification_repo.NOTIFICATION_PRIVATE_ROW_REGISTRY:
        inside |= compare.OLD_NOTIFICATION_OWNER_METADATA  # the old `_targets_owner`
    for field in sorted(inside):
        probe(f"metadata.{field}", **{f"metadata__{field}": PROBE})
    for field in ("student_id", "parent_id"):  # `_recovery_job_record_accounts`
        probe(f"filters.{field}", **{f"filters__{field}": PROBE})
        probe(f"metadata.{field}", **{f"metadata__{field}": PROBE})
        probe(f"metadata.filters.{field}", **{f"metadata__filters__{field}": PROBE})
        probe(f"metadata.result_filters.{field}", **{f"metadata__result_filters__{field}": PROBE})
    return rows


def _probes(entry: DataType) -> list[tuple[str, dict[str, Any]]]:
    return [*_pointer_probes(entry), *_rule_probes(entry)]


def _entries() -> list[DataType]:
    return [*CATALOG.values(), *UNTYPED]


@pytest.mark.parametrize("entry", _entries(), ids=lambda entry: entry.name)
def test_the_catalog_agrees_with_todays_rules_but_for_the_intended_differences(entry):
    unexplained: list[tuple[str, str, str, str]] = []
    for label, row in _probes(entry):
        for difference in compare.compare(row):
            if compare.intended(difference, row) is None:
                unexplained.append((label, difference.field, difference.kind, difference.account))
    assert not unexplained, unexplained


@pytest.mark.parametrize("entry", _entries(), ids=lambda entry: entry.name)
def test_every_declared_pointer_is_read(entry):
    for label, row in _pointer_probes(entry):
        assert PROBE in data_catalog.mentions(row), (label, row)


def test_the_rows_the_branch_gate_builds_agree_with_todays_rules():
    from test_account_deletion_branch_coverage import ACCOUNT, deleted_by_branch

    unexplained = []
    for entity_type, (_, row) in sorted(deleted_by_branch().items()):
        assert data_catalog.data_type_of(row) is not None, entity_type
        assert data_catalog.names(row, ACCOUNT), entity_type
        for difference in compare.compare(row):
            if compare.intended(difference, row) is None:
                unexplained.append((entity_type, difference.field, difference.kind))
    assert not unexplained, unexplained


def test_every_role_change_is_listed_and_every_listing_happens():
    seen: set[tuple[str, str]] = set()
    for entry in _entries():
        for _, row in _probes(entry):
            for difference in compare.compare(row):
                if difference.kind.startswith("role:"):
                    seen.update((entry.name, field) for field in difference.field.split("+"))
    assert seen == set(compare.ROLE_CHANGES), sorted(seen ^ set(compare.ROLE_CHANGES))


def test_the_comparison_script_only_reads(capsys):
    from fakes.dynamodb import FakeTable

    rows = [
        {"PK": "CONV#c", "SK": "CONV", "entity_type": "conversation", "student_id": "s1"},
        {"PK": "CONV#c", "SK": "MSG#m", "entity_type": "conversation_message", "user_id": "s2"},
        {"PK": "NEW#x", "SK": "ROW", "entity_type": "brand_new_kind", "owner_id": "s3"},
        {"PK": "SESSION#x", "SK": "ROW", "student_id": "s4"},
    ]
    table = FakeTable(page_item_cap=2)
    table.seed(*rows)
    assert compare.main([], table=table) == 0
    assert dict(table.calls) == {"scan": 2}
    report = json.loads(capsys.readouterr().out)
    assert report["rows_scanned"] == 4
    assert report["rows_unknown_to_catalog"] == {"(untyped) SESSION/ROW": 1, "brand_new_kind": 1}
    assert report["differences"] == [
        {
            "entity_type": "conversation_message",
            "field": "user_id",
            "kind": "old_only",
            "intended": "REVIEW (generic_fallback: stored rows carry it)",
            "rows": 1,
        }
    ]
    printed = json.dumps(report)
    assert not any(secret in printed for secret in ("s1", "s2", "s3", "s4", "CONV#c"))
