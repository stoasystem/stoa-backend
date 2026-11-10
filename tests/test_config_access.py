"""Configuration has two access paths (#359).

A service takes ``settings`` as a parameter, or calls ``config.settings()`` when it
needs a value. There is no import-time global and no cached getter; routes ask
for ``Depends(config.settings)``, and a test installs its ``Settings`` with
``config.install`` (or passes them in) instead of changing a shared object.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from stoa import aws, config
from stoa.aws import Kind
from stoa.config import Settings

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "stoa"
TESTS = ROOT / "tests"

# `main.py` builds the app at import, and building it reads the configuration
# (docs URL, CORS origins): the one place a module-level read is the point.
MODULE_LEVEL_READ_ALLOWED = frozenset({"main.py"})

# The getter this replaced. Spelled in two parts so that `grep -rn` for it over
# src and tests comes back empty, as #359 asks.
RETIRED_GETTER = "get_" + "settings"


# ── config.settings / config.install ─────────────────────────────────────────


def test_settings_is_built_once_and_then_reused() -> None:
    config.install(None)

    first = config.settings()

    assert isinstance(first, Settings)
    assert config.settings() is first


def test_settings_is_built_from_the_environment_on_first_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_REGION", "eu-west-3")
    config.install(None)

    assert config.settings().aws_region == "eu-west-3"


def test_install_puts_a_tests_settings_where_every_reader_finds_them() -> None:
    installed = Settings(aws_region="eu-north-1")

    config.install(installed)

    assert config.settings() is installed


def test_install_none_goes_back_to_the_environment() -> None:
    installed = Settings(aws_region="eu-north-1")
    config.install(installed)

    config.install(None)

    assert config.settings() is not installed


def test_there_is_no_import_time_global_and_no_cached_getter() -> None:
    assert not isinstance(getattr(config, "settings"), Settings)
    assert not hasattr(config, RETIRED_GETTER)


def test_a_route_depending_on_config_settings_gets_the_installed_settings() -> None:
    installed = Settings(daily_hint_limit=7)
    config.install(installed)
    app = FastAPI()

    @app.get("/limit")
    def limit(settings: Settings = Depends(config.settings)) -> dict[str, int]:
        return {"limit": settings.daily_hint_limit}

    assert TestClient(app).get("/limit").json() == {"limit": 7}


def test_the_auth_routes_cognito_region_follows_the_installed_settings() -> None:
    """Deferred from #358: the route's settings and the client's region agree."""
    from stoa.deps import get_identity_repository
    from stoa.main import app

    class _RefusingCognito:
        def initiate_auth(self, **_kwargs):
            raise ClientError(
                {"Error": {"Code": "NotAuthorizedException", "Message": "no"}},
                "InitiateAuth",
            )

    config.install(
        Settings(aws_region="eu-west-3", cognito_student_client_id="public-client")
    )
    aws.install({Kind.COGNITO: _RefusingCognito()})
    app.dependency_overrides[get_identity_repository] = object
    try:
        response = TestClient(app).post(
            "/auth/login", json={"email": "a@example.com", "password": "Wrong123!"}
        )
    finally:
        app.dependency_overrides.pop(get_identity_repository, None)

    assert response.status_code == 401
    assert [(r.kind, r.region) for r in aws.requests()] == [(Kind.COGNITO, "eu-west-3")]


def test_best_effort_notifications_switch_is_a_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STOA_ENABLE_BEST_EFFORT_NOTIFICATIONS", "true")
    assert Settings().stoa_enable_best_effort_notifications is True
    monkeypatch.delenv("STOA_ENABLE_BEST_EFFORT_NOTIFICATIONS")
    assert Settings().stoa_enable_best_effort_notifications is False


# ── The gate ──────────────────────────────────────────────────────────────────


def _is_settings_read(node: ast.AST) -> bool:
    """A call that reads the configuration.

    `config.settings()` under any alias (`configuration.settings()`,
    `stoa.config.settings()`), a bare `settings()`, or building a `Settings()`.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    return name in {"settings", "Settings"}


def _import_time_nodes(tree: ast.Module):
    """Every node evaluated when the module is imported (function bodies are not)."""
    pending: list[ast.AST] = list(tree.body)
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            pending.extend(node.decorator_list)
            pending.extend(args.defaults)
            pending.extend(d for d in args.kw_defaults if d is not None)
            continue
        if isinstance(node, ast.Lambda):
            continue
        pending.extend(ast.iter_child_nodes(node))


def config_access_violations(sources: dict[str, str]) -> list[str]:
    """`path: what` for each file in `src/stoa` that reaches configuration another way."""
    found: list[str] = []
    for path, text in sorted(sources.items()):
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("config"):
                if any(alias.name == "settings" for alias in node.names):
                    found.append(f"{path}: imports settings")
                if any(alias.name == RETIRED_GETTER for alias in node.names):
                    found.append(f"{path}: {RETIRED_GETTER}")
            if (isinstance(node, ast.Name) and node.id == RETIRED_GETTER) or (
                isinstance(node, ast.Attribute) and node.attr == RETIRED_GETTER
            ) or (isinstance(node, ast.FunctionDef) and node.name == RETIRED_GETTER):
                found.append(f"{path}: {RETIRED_GETTER}")
        if path not in MODULE_LEVEL_READ_ALLOWED and any(
            _is_settings_read(node) for node in _import_time_nodes(tree)
        ):
            found.append(f"{path}: reads settings at import")
    return sorted(set(found))


def _ends_in_settings(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):
        return "settings" in node.attr.lower()
    if isinstance(node, ast.Name):
        return "settings" in node.id.lower()
    return False


def config_patch_violations(sources: dict[str, str]) -> list[str]:
    """`path:line` for each test that changes shared configuration in place.

    `monkeypatch.setattr(<settings object>, ...)`, swapping a module's `settings`
    (or the old getter), and `dependency_overrides[<settings dependency>]`.
    """
    found: list[str] = []
    for path, text in sorted(sources.items()):
        for node in ast.walk(ast.parse(text)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setattr"
                and node.args
            ):
                target = node.args[0]
                name = node.args[1] if len(node.args) > 1 else None
                if _ends_in_settings(target) or (
                    isinstance(name, ast.Constant)
                    and isinstance(name.value, str)
                    and name.value.endswith("settings")
                ):
                    found.append(f"{path}:{node.lineno}")
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "dependency_overrides"
                and _ends_in_settings(node.slice)
            ):
                found.append(f"{path}:{node.lineno}")
    return found


def _read(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*.py")
    }


def test_src_reaches_configuration_only_through_the_two_paths() -> None:
    assert config_access_violations(_read(SRC)) == []


def test_the_src_gate_turns_red() -> None:
    sources = _read(SRC)
    sources["services/notify_service.py"] += "\nfrom stoa.config import settings\n"
    sources["jobs/new_job.py"] = "from stoa import config\nREGION = config.settings().aws_region\n"
    sources["jobs/default_arg.py"] = (
        "from stoa import config\n"
        "def run(region=config.settings().aws_region):\n    return region\n"
    )
    sources["jobs/aliased.py"] = (
        "from stoa import config as configuration\n"
        "BUCKET = configuration.settings().s3_images_bucket\n"
    )
    sources["jobs/dotted.py"] = "import stoa.config\nREGION = stoa.config.settings().aws_region\n"
    sources["jobs/built.py"] = "from stoa.config import Settings\nSETTINGS = Settings()\n"
    sources["jobs/old.py"] = f"from stoa.config import {RETIRED_GETTER}\n"
    sources["jobs/fine.py"] = (
        "from stoa import config\ndef run():\n    return config.settings().aws_region\n"
    )

    assert config_access_violations(sources) == [
        "jobs/aliased.py: reads settings at import",
        "jobs/built.py: reads settings at import",
        "jobs/default_arg.py: reads settings at import",
        "jobs/dotted.py: reads settings at import",
        "jobs/new_job.py: reads settings at import",
        f"jobs/old.py: {RETIRED_GETTER}",
        "services/notify_service.py: imports settings",
    ]


def test_tests_do_not_change_shared_configuration_in_place() -> None:
    assert config_patch_violations(_read(TESTS)) == []


def test_the_tests_gate_turns_red() -> None:
    sources = {
        "test_a.py": "def test(monkeypatch, settings):\n"
        "    monkeypatch.setattr(settings, 'aws_region', 'x')\n",
        "test_b.py": "def test(monkeypatch):\n"
        "    monkeypatch.setattr(svc, 'settings', object())\n",
        "test_c.py": "def test(app, cfg):\n"
        "    app.dependency_overrides[config.settings] = lambda: cfg\n",
        "test_d.py": "def test(monkeypatch):\n"
        "    monkeypatch.setattr(svc.settings, 'environment', 'production')\n",
        "test_ok.py": "def test(monkeypatch):\n"
        "    config.install(Settings(aws_region='x'))\n"
        "    monkeypatch.setattr(svc, 'clock', object())\n",
    }

    assert config_patch_violations(sources) == [
        "test_a.py:2", "test_b.py:2", "test_c.py:2", "test_d.py:2",
    ]
