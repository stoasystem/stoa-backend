"""Shared pytest fixtures for the repository test suite."""

from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path

import pytest

from security.conftest import *  # noqa: F403


pytest_plugins = ("scripts.phase474_pytest_guard",)


@pytest.fixture(scope="session", autouse=True)
def _phase474_formal_runtime() -> object:
    """Freeze time and deny in-process sockets only for formal release runs."""
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
