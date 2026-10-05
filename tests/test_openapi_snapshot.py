"""The committed OpenAPI snapshot is the contract the frontend checks its mocks against.

stoasystem/stoa-backend#80. The frontend's dist e2e (stoasystem/stoa-frontend#29)
runs against a mock backend and validates the mock's responses with
`docs/api/openapi.json`, fetched live from `main`. A snapshot that falls behind
the code would let the mock drift unseen, so the suite fails when they differ.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "api" / "openapi.json"
SCRIPT = ROOT / "scripts" / "generate_openapi_snapshot.py"


def test_the_committed_snapshot_is_what_the_app_serves() -> None:
    import generate_openapi_snapshot

    assert SNAPSHOT.read_text() == generate_openapi_snapshot.render_snapshot()


def test_the_snapshot_carries_each_route_s_authorization() -> None:
    schema = json.loads(SNAPSHOT.read_text())

    login = schema["paths"]["/auth/me"]["get"]
    assert "x-stoa-authorization" in login


def test_check_mode_fails_on_a_stale_snapshot(tmp_path: Path) -> None:
    stale = tmp_path / "openapi.json"
    stale.write_text(SNAPSHOT.read_text().replace('"title": "', '"title": "stale ', 1))

    fresh = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--output", str(SNAPSHOT)],
        cwd=ROOT, capture_output=True, text=True,
    )
    drifted = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--output", str(stale)],
        cwd=ROOT, capture_output=True, text=True,
    )

    assert fresh.returncode == 0, fresh.stderr
    assert drifted.returncode == 1
    assert "openapi.json" in drifted.stderr
