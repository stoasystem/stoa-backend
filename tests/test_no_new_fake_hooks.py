"""No new `getattr(table|target|repository, ...)` hooks for test doubles (#629).

A hook such as `hook = getattr(target, "claim_delivery_intent", None)` lets a fake
table or fake repository stand in for one step. The real boto3 Table has no such
attribute, so production always takes the other branch, and a fake that lacks the
method silently skips the step: `release_resource_attachments` ran without its
retention fence for any repository without `activate_retention_fence`.

#629 removed the fifteen hooks no fake used any more. The ones listed below are
still in use; candidate I (#634) removes the account-deletion ones and candidate C
(#638) the notification one. The attachment service's went with its three leave
actions (#653). A hook not listed may not appear, and a listed hook that is gone
must be taken off.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = ROOT / "src" / "stoa" / "db" / "repositories"
ATTACHMENT_SERVICE = ROOT / "src" / "stoa" / "services" / "attachment_service.py"
SEAMS = {"table", "target", "repository"}

Hook = tuple[str, str, str]  # (file, enclosing function, attribute asked for)

ACCOUNT_DELETION = "src/stoa/db/repositories/account_deletion_repo.py"
NOTIFICATION = "src/stoa/db/repositories/notification_repo.py"

ALLOWED: Counter[Hook] = Counter(
    {
        # Candidate I (#634).
        (ACCOUNT_DELETION, "ensure_active_account_fence", "'backfill_account_fence'"): 1,
        (ACCOUNT_DELETION, "begin_account_deletion", "'begin_account_deletion'"): 1,
        (ACCOUNT_DELETION, "get_command_by_id", "'get_command_by_id'"): 1,
        (
            ACCOUNT_DELETION,
            "replace_with_deletion_tombstone",
            "'replace_with_deletion_tombstone'",
        ): 1,
        (ACCOUNT_DELETION, "delete_owned_row", "'delete_owned_row'"): 1,
        (ACCOUNT_DELETION, "scrub_parent_profile_child", "'scrub_parent_profile_child'"): 1,
        (ACCOUNT_DELETION, "terminalize_identity_row", "'replace_with_deletion_tombstone'"): 1,
        (ACCOUNT_DELETION, "persist_branch_result", "'persist_branch_result'"): 1,
        (ACCOUNT_DELETION, "finalize_account_deletion", "'get_deletion_command'"): 1,
        (ACCOUNT_DELETION, "finalize_account_deletion", "'finalize_account_deletion'"): 2,
        # Candidate C (#638).
        (
            NOTIFICATION,
            "_replace_notification_owner_tombstone",
            "'replace_notification_tombstone'",
        ): 1,
        # Other repositories, as found when the gate was added.
        (
            "src/stoa/db/repositories/adaptive_learning_repo.py",
            "scrub_adaptive_private_row",
            "'replace_learning_tombstone'",
        ): 1,
        ("src/stoa/db/repositories/allowance_repo.py", "_strong_get", "'get_item'"): 1,
        (
            "src/stoa/db/repositories/attachment_repo.py",
            "scrub_conversation_private_row",
            "'scrub_conversation_private_row'",
        ): 1,
        ("src/stoa/db/repositories/identity_repo.py", "create_identity_binding", "'meta'"): 1,
        (
            "src/stoa/db/repositories/moderation_repo.py",
            "scrub_moderation_row",
            "'scrub_moderation_row'",
        ): 1,
        (
            "src/stoa/db/repositories/practice_repo.py",
            "scrub_practice_private_row",
            "'replace_learning_tombstone'",
        ): 1,
        (
            "src/stoa/db/repositories/public_identity_repo.py",
            "create_or_get_public_identity_command",
            "'meta'",
        ): 1,
        ("src/stoa/db/repositories/public_identity_repo.py", "require_command_fence", "'meta'"): 1,
        (
            "src/stoa/db/repositories/websocket_repo.py",
            "revoke_account_connection",
            "'delete_connection_for_account'",
        ): 1,
        ("src/stoa/db/repositories/weekly_counter.py", "read", "'get_item'"): 1,
    }
)


def _hooks_in(source: str, relative: str) -> Counter[Hook]:
    found: Counter[Hook] = Counter()

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            enclosing = (
                child.name
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                else function
            )
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "getattr"
                and len(child.args) >= 2
                and isinstance(child.args[0], ast.Name)
                and child.args[0].id in SEAMS
            ):
                found[(relative, enclosing, ast.unparse(child.args[1]))] += 1
            visit(child, enclosing)

    visit(ast.parse(source), "<module>")
    return found


def _hooks() -> Counter[Hook]:
    found: Counter[Hook] = Counter()
    for path in [*sorted(REPOSITORIES.rglob("*.py")), ATTACHMENT_SERVICE]:
        relative = path.relative_to(ROOT).as_posix()
        found += _hooks_in(path.read_text(encoding="utf-8"), relative)
    return found


def test_no_new_hook_lets_a_fake_replace_a_step():
    new = _hooks() - ALLOWED
    assert not new, (
        "call the real implementation and give the fake the method instead: "
        f"{sorted(new)}"
    )


def test_the_allowlist_names_only_hooks_that_are_still_there():
    stale = ALLOWED - _hooks()
    assert not stale, f"hook removed; take it off ALLOWED: {sorted(stale)}"


def test_the_gate_sees_what_it_guards():
    source = (
        "def step(target, repository, table):\n"
        "    hook = getattr(target, 'claim_delivery_intent', None)\n"
        "    probe = getattr(repository, name, None)\n"
        "    meta = getattr(table, 'meta')\n"
        "    read = getattr(body, 'read', None)\n"
    )
    assert _hooks_in(source, "f.py") == Counter(
        {
            ("f.py", "step", "'claim_delivery_intent'"): 1,
            ("f.py", "step", "name"): 1,
            ("f.py", "step", "'meta'"): 1,
        }
    )
