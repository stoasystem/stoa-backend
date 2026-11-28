"""Plan 473-32 contracts for conversation writer fencing and deletion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fakes.ask_question import DELETED_STUDENT as STUDENT_ID
from fakes.ask_question import _private_message as _message
from fakes.dynamodb import from_wire
from stoa.db.repositories import attachment_repo
from stoa.services import learning_session


def _contract(name: str) -> Any:
    value = getattr(attachment_repo, name, None)
    if value is None:
        pytest.fail(f"conversation deletion contract {name} is not implemented")
    return value


def test_every_conversation_write_transaction_starts_with_exact_account_fence() -> None:
    # The session's fenced write moved to learning_session with the record (#226);
    # the table gateway puts the fence in front of it (#297).
    operations: list[dict[str, Any]] = []

    class _Table:
        def transact_write_items(self, *, TransactItems: list[dict[str, Any]]) -> None:  # noqa: N803
            operations.extend(from_wire(TransactItems))

    learning_session._store.create_conversation_record(
        _message(),
        owner_id=STUDENT_ID,
        generation=7,
        table=_Table(),
    )
    fence = operations[0]["ConditionCheck"]
    assert fence["Key"] == {"PK": f"USER#{STUDENT_ID}", "SK": "ACCOUNT_FENCE"}
    assert fence["ExpressionAttributeValues"][":generation"] == 7
    put = operations[1]["Put"]
    assert put["Item"]["owner_id"] == STUDENT_ID
    assert put["Item"]["account_fence_generation"] == 7


def test_direct_router_writes_are_forbidden_by_static_writer_gate() -> None:
    source = Path("src/stoa/routers/conversations.py").read_text()
    assert ".put_item(" not in source
    assert ".update_item(" not in source
    # A conversation is opened through the session's own fenced write (#226).
    assert "learning_session.open(" in source
    # The help request is written by its own module (#189), through the same
    # fenced conversation writes, never a direct put or update.
    assert "help_requests.ask(" in source
    help_source = Path("src/stoa/services/help_requests.py").read_text()
    assert ".put_item(" not in help_source
    assert ".update_item(" not in help_source
    assert "build_conversation_write_transaction" in help_source
    # The question package writes through its repository, `_store.py`, alone
    # (#204); the modules in front of it never put or update a row themselves.
    package = Path("src/stoa/services/ask_question")
    modules = sorted(path for path in package.glob("*.py") if path.name != "_store.py")
    assert {"__init__.py", "_answering.py", "_sweep.py"} <= {path.name for path in modules}
    for path in modules:
        package_source = path.read_text(encoding="utf-8")
        assert ".put_item(" not in package_source, path.name
        assert ".update_item(" not in package_source, path.name
    # So does the learning session's (#226): only `_store.py` reaches the table.
    session = Path("src/stoa/services/learning_session")
    session_modules = sorted(
        path for path in session.glob("*.py") if path.name != "_store.py"
    )
    assert {"__init__.py", "_history.py"} <= {path.name for path in session_modules}
    for path in session_modules:
        session_source = path.read_text(encoding="utf-8")
        assert ".put_item(" not in session_source, path.name
        assert ".update_item(" not in session_source, path.name
    # Every message row is made by `learning_session.append` (#227): the
    # teacher's reply, the system message that opens a help request and the
    # question's student and assistant messages. None of them builds the row.
    # The teacher's reply is appended by `help_requests.reply` (#233), so the
    # teacher routes append nothing themselves. (`teachers.py` still puts rows
    # of its own through `_teacher_put`, so it is not held to "no `.put_item(`"
    # here.)
    teacher_source = Path("src/stoa/routers/teachers.py").read_text(encoding="utf-8")
    assert "learning_session.append(" not in teacher_source
    assert '"SK": f"MSG#' not in teacher_source
    assert "conversation-message.v1" not in teacher_source
    assert '"entity_type": "conversation_message"' not in teacher_source
    assert "learning_session.append(" in help_source
    answering_source = Path("src/stoa/services/ask_question/_answering.py").read_text(
        encoding="utf-8"
    )
    assert "learning_session.append(" in answering_source
    # The message row's shape is named only inside the session package (#228).
    # The account-deletion inventory names the entity type to find the rows it
    # scrubs, and the data type catalog lists every type (#587); they are the
    # places outside the package allowed to.
    inventory = {
        Path("src/stoa/db/repositories/attachment_repo.py"),
        Path("src/stoa/db/data_catalog.py"),
    }
    for path in sorted(Path("src/stoa").rglob("*.py")):
        if session in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        assert "conversation-message.v1" not in text, path
        assert '"entity_type": "conversation_message"' not in text, path
        if path not in inventory:
            assert '"conversation_message"' not in text, path
        # The message key prefix belongs to the session's store alone.
        assert "MSG#" not in text, path
    for path in session_modules:
        assert "MSG#" not in path.read_text(encoding="utf-8"), path.name


