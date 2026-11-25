"""Shared pytest fixtures for the repository test suite."""

from __future__ import annotations

import os

import pytest

from security.conftest import *  # noqa: F403


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
    monkeypatch.setattr(adaptive_learning_service, "weak_topics", lambda *_a, **_k: [])
    monkeypatch.setattr(star_map_candidates, "for_student", lambda *_a, **_k: None)


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
    clears = (
        db_table.client.cache_clear,
        db_table._real_table.cache_clear,
        db_table._resource.cache_clear,
    )
    for clear in clears:
        clear()
    yield
    for clear in clears:
        clear()


@pytest.fixture(autouse=True)
def _no_aws_clients():
    """Every test starts with no AWS client installed (#358).

    `stoa.aws.client` is the one place a client is built, and in a test it hands
    out only what the test put there with `stoa.aws.install`: asking for any
    other kind raises `NotInstalled` rather than reaching AWS. A test that wants
    real botocore clients (moto, Stubber, a presigned URL) calls
    `stoa.aws.install(None)`.
    """
    from stoa import aws

    aws.reset_for_test()
    yield
    aws.reset_for_test()


@pytest.fixture(autouse=True)
def _no_model_call_adapter():
    """Every test starts with no model-call adapter installed (#436).

    A test that asks the model installs its own with
    `stoa.services.model_call.install`, usually the in-memory `FakeAdapter`;
    one that does not raises `NotInstalled` rather than reaching Bedrock.
    """
    from stoa.services import model_call

    model_call.reset_for_test()
    yield
    model_call.reset_for_test()


@pytest.fixture(autouse=True)
def _configuration_from_the_environment():
    """Every test starts from settings built from the environment (#359).

    A test that needs other values installs them with `stoa.config.install` or
    passes them in; whatever it installed is gone before the next test.
    """
    from stoa import config

    config.install(None)
    yield
    config.install(None)


@pytest.fixture(autouse=True)
def _no_request_locale():
    """Every test starts with no request language bound.

    `locale_service` keeps the language a request asked for in a ContextVar that
    `main`'s middleware sets on every request. A test that sets it by hand, or
    drives an app built without that middleware, would otherwise leave its
    language for whichever test the same worker runs next - which then gets its
    error messages in English or French instead of the default.
    """
    from stoa.services import locale_service

    locale_service.set_request_locale(None)
    yield
    locale_service.set_request_locale(None)


@pytest.fixture
def link_rows(fake_table):
    """Link rows the relationship judge reads, served as the link table (#208).

    `link_rows.link(parent, student)` makes a current relationship as far as the
    rows go; the judge still asks `user_repo.get_user` about both accounts.
    """
    from fakes.links import LinkRows

    return LinkRows(fake_table)
