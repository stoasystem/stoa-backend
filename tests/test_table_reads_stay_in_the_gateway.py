"""Reads, paging and conditional refusals reach DynamoDB through the table gateway (#298).

The table gateway (`stoa.db.table`, #210) is where the table is taken from, where a
read goes on page after page, and where a refusal is judged. A module below
`src/stoa` that does one of these itself has started a second one:

- `get_table`: calls `get_table()` for a table of its own instead of reading through
  the gateway;
- `paging`: names `ExclusiveStartKey`, which is a paging loop of its own
  (`db_table.pages` / `db_table.rows` are the ones);
- `conditional_check`: matches the `ConditionalCheckFailedException` string instead of
  catching the gateway's `WriteRefused`.

`ALLOWED` names every file that still does, and which of the three. It is grouped
by domain, and each group is one batch migration of #210: a batch moves its files
onto the gateway and deletes their lines - a file may not keep a rule it no longer
breaks, and no file may start breaking one. When the batches are done the only
entry left is `services/subscription_service.py`, while payments are frozen.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "stoa"
GATEWAY = "db/table.py"

RULES = {
    # A call, not the definition in `db/dynamodb.py` and not a name passed along.
    "get_table": re.compile(r"(?<!def )\bget_table\(\)"),
    "paging": re.compile(r"\bExclusiveStartKey\b"),
    "conditional_check": re.compile(r"ConditionalCheckFailedException"),
}

ALLOWED: dict[str, dict[str, set[str]]] = {
    "accounts and identity": {
        "db/repositories/account_deletion_repo.py": {"get_table", "conditional_check"},
        "db/repositories/account_email_claim_repo.py": {"get_table"},
        "db/repositories/account_invitation_repo.py": {"get_table", "paging", "conditional_check"},
        "db/repositories/account_number_repo.py": {"get_table", "conditional_check"},
        "db/repositories/capability_repo.py": {"paging"},
        "db/repositories/identity_repo.py": {"get_table", "conditional_check"},
        "db/repositories/parent_link_repo.py": {"get_table"},
        "db/repositories/privileged_identity_repo.py": {"get_table", "conditional_check"},
        "db/repositories/public_identity_repo.py": {"get_table", "conditional_check"},
        "db/repositories/security_audit_repo.py": {"get_table", "conditional_check"},
        "db/repositories/teacher_application_repo.py": {"get_table", "conditional_check"},
        "db/repositories/user_repo.py": {"get_table", "paging"},
        "routers/auth.py": {"get_table"},
        "services/account_deletion_service.py": {"get_table"},
        "services/account_lifecycle.py": {"get_table"},
        "services/account_provisioning_service.py": {"get_table"},
        "services/current_relationship.py": {"get_table", "paging"},
        "services/password_change_code_service.py": {"get_table", "conditional_check"},
        "services/rate_limit.py": {"get_table"},
    },
    "learning and practice": {
        "db/repositories/adaptive_learning_repo.py": {"get_table", "paging", "conditional_check"},
        "db/repositories/ai_teacher_tools_repo.py": {"get_table", "paging"},
        "db/repositories/allowance_repo.py": {"get_table", "paging"},
        "db/repositories/asked_knowledge_repo.py": {"get_table", "paging"},
        "db/repositories/curriculum_analytics_repo.py": {"get_table", "paging"},
        "db/repositories/curriculum_ops_repo.py": {"get_table", "paging", "conditional_check"},
        "db/repositories/practice_repo.py": {"get_table", "paging"},
        "db/repositories/question_repo.py": {"get_table", "paging"},
        "db/repositories/review_repo.py": {"get_table"},
        "db/repositories/usage_ledger_repo.py": {"get_table", "paging", "conditional_check"},
        "routers/conversations.py": {"get_table", "paging"},
        "routers/students.py": {"get_table"},
        "routers/teachers.py": {"get_table"},
        "services/ask_question/_answering.py": {"get_table"},
        "services/ask_question/_store.py": {"get_table", "paging"},
        "services/help_requests.py": {"get_table", "paging"},
        "services/learning_session/_store.py": {"get_table", "paging"},
        "services/teacher_dispatch_service.py": {"get_table", "paging"},
        "services/teacher_support_allowance_service.py": {"get_table", "conditional_check"},
    },
    "reports and notifications": {
        "db/repositories/notification_repo.py": {"get_table", "conditional_check"},
        "db/repositories/report_repo.py": {"get_table", "paging", "conditional_check"},
        "db/repositories/websocket_repo.py": {"get_table"},
        "routers/parents.py": {"get_table", "paging"},
        "jobs/weekly_reports.py": {"get_table"},
        "services/notification_service.py": {"get_table"},
        "services/report_service.py": {"get_table", "paging"},
    },
    "billing and entitlements": {
        "db/repositories/billing_fact_repo.py": {"get_table"},
        "db/repositories/checkout_command_repo.py": {"get_table"},
        "jobs/migrate_billing_plan_identity.py": {"get_table", "conditional_check"},
        "services/billing_reconciliation_service.py": {"get_table"},
        "services/entitlement_service.py": {"get_table"},
        "services/free_trial_service.py": {"get_table"},
        "services/paid_entitlement_service.py": {"get_table"},
    },
    "payments, frozen (stays until payments resume)": {
        "services/subscription_service.py": {"get_table", "paging", "conditional_check"},
    },
}


def _breaks(text: str) -> set[str]:
    return {rule for rule, pattern in RULES.items() if pattern.search(text)}


def _offenders() -> dict[str, set[str]]:
    offenders = {}
    for path in sorted(SOURCE.rglob("*.py")):
        relative = path.relative_to(SOURCE).as_posix()
        if relative == GATEWAY:
            continue
        found = _breaks(path.read_text(encoding="utf-8"))
        if found:
            offenders[relative] = found
    return offenders


def _allowed() -> dict[str, set[str]]:
    return {path: rules for group in ALLOWED.values() for path, rules in group.items()}


def test_no_module_starts_reading_or_judging_the_table_itself():
    allowed = _allowed()
    new = {
        path: sorted(rules - allowed.get(path, set()))
        for path, rules in _offenders().items()
        if rules - allowed.get(path, set())
    }
    assert not new, f"read and judge through stoa.db.table instead: {new}"


def test_the_allowlist_names_only_what_files_still_do():
    offenders = _offenders()
    stale = {
        path: sorted(rules - offenders.get(path, set()))
        for path, rules in _allowed().items()
        if rules - offenders.get(path, set())
    }
    assert not stale, f"no longer needed; remove from ALLOWED: {stale}"


def test_each_file_is_in_one_batch():
    paths = [path for group in ALLOWED.values() for path in group]
    assert len(paths) == len(set(paths))


def test_the_gateway_is_where_paging_happens():
    gateway = (SOURCE / GATEWAY).read_text(encoding="utf-8")
    assert RULES["paging"].search(gateway)


def test_the_gate_sees_what_it_guards():
    assert _breaks("    target = table or get_table()") == {"get_table"}
    assert _breaks('        request["ExclusiveStartKey"] = cursor') == {"paging"}
    assert _breaks('    if code == "ConditionalCheckFailedException":') == {"conditional_check"}
    assert not _breaks("def get_table() -> object:")
    assert not _breaks("table_factory=get_table,")
    assert not _breaks('for page in db_table.pages("scan", start=cursor):')
