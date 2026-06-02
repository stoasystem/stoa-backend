"""Weekly report scheduled Lambda entrypoint.

The real generation pipeline is implemented in later v1.1 phases. This stub
keeps the CDK scheduled Lambda target importable as soon as infrastructure is
deployed.
"""

from typing import Any


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Return a safe no-op response until the report job is implemented."""
    return {
        "status": "not_implemented",
        "message": "Weekly report generation is not implemented yet.",
        "attempted": 0,
        "generated": 0,
        "skipped_existing": 0,
        "email_sent": 0,
        "failed": 0,
    }
