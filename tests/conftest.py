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


@pytest.fixture
def stub_memory_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep AI memory personalisation out of message-command tests.

    `conversations._execute_message_command` enriches the AI prompt with the
    student's weak topics, which costs three table reads. Unstubbed, that turns
    every message-command test into a network round trip and can push a
    concurrent duplicate past its bounded replay wait.
    """
    from stoa.services import adaptive_learning_service

    monkeypatch.setattr(
        adaptive_learning_service,
        "get_memory_summary",
        lambda **_kwargs: {"weakTopics": [], "recommendations": [], "memorySnapshots": []},
    )


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


class _EmptyParentLinkTable:
    """A link table holding nothing, so an unstubbed read cannot reach real DynamoDB."""

    def get_item(self, **_kwargs: object) -> dict[str, object]:
        return {}

    def query(self, **_kwargs: object) -> dict[str, object]:
        return {"Items": []}

    def transact_account_deletion(self, _operations: object) -> None:
        raise AssertionError(
            "this test writes parent links; install its own parent_link_repo.get_table"
        )


@pytest.fixture(autouse=True)
def _default_parent_link_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every downstream reader of the many-to-many links now consults them.

    Without a default, a test that sets up no links falls through to the live
    `get_table()` and issues a real DynamoDB request. Tests that need link rows
    patch the same attribute afterwards and win.
    """
    from stoa.db.repositories import parent_link_repo

    monkeypatch.setattr(parent_link_repo, "get_table", _EmptyParentLinkTable)
