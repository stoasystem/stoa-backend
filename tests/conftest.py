"""Shared pytest fixtures for the repository test suite."""

from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path

import pytest

from security.conftest import *  # noqa: F403


pytest_plugins = ("scripts.phase474_pytest_guard",)


# Credential discovery is a network call, and the suite was only ever quiet
# about it because whoever ran it had credentials lying around. Without them
# boto3 falls through to the instance metadata service at 169.254.169.254 —
# which is what CI does, and what the socket guard then refuses. Pinning
# throwaway credentials and switching that last resort off keeps resolution
# entirely local, so a test that reaches AWS fails for reaching AWS rather than
# for the machine it happens to be running on.
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-central-2")


def _render_rule_violations_like_the_application() -> None:
    """Give every test's bare `FastAPI()` the handler `stoa.main` installs.

    Most route tests mount one router on an application of their own. A rule
    violation is rendered by an application-level handler, not by the router,
    so without it those applications would answer every refusal with a 500.
    """
    import fastapi

    from stoa.rule_violation import install_rule_violation_handler

    if getattr(fastapi.FastAPI.__init__, "_renders_rule_violations", False):
        return
    original = fastapi.FastAPI.__init__

    def __init__(self, *args, **kwargs):
        original(self, *args, **kwargs)
        install_rule_violation_handler(self)

    __init__._renders_rule_violations = True  # type: ignore[attr-defined]
    fastapi.FastAPI.__init__ = __init__  # type: ignore[method-assign]


_render_rule_violations_like_the_application()


@pytest.fixture
def stub_memory_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep AI memory personalisation out of message-command tests.

    `ask_question._answering.commit_message_command` enriches the AI prompt with the
    student's weak topics, which costs three table reads, and with the stars on
    the student's map (#142), which costs more. Unstubbed, that turns every
    message-command test into a network round trip and can push a concurrent
    duplicate past its bounded replay wait. The map is left out as unreadable.
    """
    from stoa.services import adaptive_learning_service, star_map_candidates

    monkeypatch.setattr(
        adaptive_learning_service,
        "get_memory_summary",
        lambda **_kwargs: {"weakTopics": [], "recommendations": [], "memorySnapshots": []},
    )
    monkeypatch.setattr(star_map_candidates, "for_student", lambda *_a, **_k: None)


@pytest.fixture(scope="session", autouse=True)
def _phase474_formal_runtime() -> object:
    """Freeze time and deny sockets for the complete formal pytest lifecycle.

    The formal argv disables pytest-socket's per-item hooks because its teardown
    restores real sockets before fixture finalizers. This session fixture owns
    the socket restriction until all finalizers have completed.
    """
    if os.environ.get("STOA_PHASE474_HERMETIC") != "1":
        yield
        return

    from pytest_socket import disable_socket, enable_socket
    import time_machine

    clock = os.environ["STOA_PHASE474_CLOCK"]
    credentials_root = Path(os.environ["STOA_PHASE474_CREDENTIAL_ROOT"])
    assert os.environ.get("AWS_EC2_METADATA_DISABLED") == "true"
    assert Path(os.environ["AWS_SHARED_CREDENTIALS_FILE"]).parent == credentials_root
    assert Path(os.environ["AWS_CONFIG_FILE"]).parent == credentials_root

    with ExitStack() as stack:
        stack.enter_context(time_machine.travel(clock, tick=False))
        disable_socket(allow_unix_socket=True)
        try:
            yield
        finally:
            enable_socket()


@pytest.fixture(autouse=True)
def _empty_table():
    """Every test starts with an empty `FakeTable` where the real table would be.

    The table gateway takes its table from one place (`stoa.db.table.install`),
    and so does every module reading through `get_table()`. Without this, a test
    that set nothing up fell through to the live table and issued a real
    DynamoDB request; with it, such a test reads an empty table instead. A test
    that needs rows takes `fake_table`. A module whose own `get_table` a test
    patches still answers from the patch - those patches go with the batches of
    #210 that move each domain onto the gateway.
    """
    from fakes.dynamodb import FakeTable
    from stoa.db import table as db_table

    db_table.install(FakeTable())
    yield
    db_table.install(None)


@pytest.fixture
def fake_table():
    """A `FakeTable` installed in the gateway for this test, and handed to it."""
    from fakes.dynamodb import FakeTable
    from stoa.db import table as db_table

    table = FakeTable()
    db_table.install(table)
    return table


@pytest.fixture(autouse=True)
def _fresh_gateway_clients():
    """The table gateway builds its table and client once per process.

    A test runs under its own fake credentials and, for moto, its own mock, so
    a client built by an earlier test must not carry over into it.
    """
    from stoa.db import table as db_table

    # Held now: a test may patch `db_table.client` itself, and the patch can
    # still be in place when this fixture is torn down.
    clears = (db_table.client.cache_clear, db_table._real_table.cache_clear)
    for clear in clears:
        clear()
    yield
    for clear in clears:
        clear()


@pytest.fixture
def link_rows(fake_table):
    """Link rows the relationship judge reads, served as the link table (#208).

    `link_rows.link(parent, student)` makes a current relationship as far as the
    rows go; the judge still asks `user_repo.get_user` about both accounts.
    """
    from fakes.links import LinkRows

    return LinkRows(fake_table)
