"""What the API Lambda loads at a cold start (#306).

Init on Lambda is almost entirely `import stoa.main`, and every login after a
cold start waits for it. Libraries only an upload needs are imported where the
upload is handled, and the OpenAPI error bodies name the question's codes
without loading the whole question package. Each check runs in a fresh process,
since this one has imported everything already.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

_PROBE = """
import importlib, sys
importlib.import_module(sys.argv[1])
print(" ".join(name for name in sys.argv[2:] if name in sys.modules))
"""


def _loaded(module: str, *names: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, module, *names],
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **os.environ,
            "AWS_DEFAULT_REGION": "eu-central-2",
            # This checkout's source, not whichever one the environment installed.
            "PYTHONPATH": os.pathsep.join([str(SRC), os.environ.get("PYTHONPATH", "")]),
        },
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


@pytest.mark.parametrize("library", ["pypdf", "PIL"])
def test_the_api_does_not_load_an_upload_only_library_at_start(library: str) -> None:
    assert _loaded("stoa.main", library) == []


def test_the_error_bodies_do_not_load_the_question_package() -> None:
    assert _loaded("stoa.models.error", "stoa.services.ask_question") == []
