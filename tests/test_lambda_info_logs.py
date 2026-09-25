"""INFO lines from our own code reach the Lambda's logs (E29).

The Lambda Python runtime leaves the root logger at WARNING and configures
nothing else, so every `logger.info` in `stoa` was dropped: the sweep's summary
line (E26) and the deletion cycle line (E16) never appeared. Each deployed
handler is imported in a fresh process whose root logger is set up the way
the runtime sets it up, and one INFO line from its own module must come out.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

DEPLOYED_HANDLERS = (
    "stoa.main",
    "stoa.jobs.weekly_reports",
    "stoa.jobs.dispatch_reconciler",
    "stoa.jobs.account_deletion",
    "stoa.jobs.conversation_generation",
)

_PROBE = """
import importlib, logging, sys
logging.basicConfig(level=logging.WARNING, stream=sys.stdout, format="%(levelname)s %(message)s")
module = importlib.import_module(sys.argv[1])
logging.getLogger(module.__name__).info("probe_info_line")
logging.getLogger("botocore").info("third_party_info_line")
"""


@pytest.mark.parametrize("module", DEPLOYED_HANDLERS)
def test_a_deployed_handler_writes_its_info_lines(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, module],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "AWS_DEFAULT_REGION": "eu-central-2"},
    )

    assert result.returncode == 0, result.stderr
    assert "INFO probe_info_line" in result.stdout
    # Only our own loggers: the SDKs stay as quiet as before.
    assert "third_party_info_line" not in result.stdout
