"""Month-to-date AWS cost from Cost Explorer, by service bucket (card 134-R2)."""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from botocore.config import Config

from stoa import aws

# Cost Explorer has one endpoint, in us-east-1.
CE_REGION = "us-east-1"
SERVICES = ("ai", "database", "other")
PAGE_BUDGET = 10

_READ_CONFIG = Config(connect_timeout=2, read_timeout=5, retries={"mode": "standard", "total_max_attempts": 2})

_installed: dict[str, Any] = {}


def install(ce: Any = None) -> None:
    """Put a double where the Cost Explorer client would be; no argument clears."""
    _installed.clear()
    if ce is not None:
        _installed["ce"] = ce


@lru_cache
def _real_client() -> Any:
    return aws.session().client("ce", region_name=CE_REGION, config=_READ_CONFIG)


def _client() -> Any:
    return _installed["ce"] if "ce" in _installed else _real_client()


def service_bucket(name: str) -> str:
    if "Bedrock" in name:
        return "ai"
    if "DynamoDB" in name:
        return "database"
    return "other"


def month_to_date(today: date) -> dict[str, float]:
    """UnblendedCost from the 1st of `today`'s month through `today`, per bucket; raises on failure."""
    request: dict[str, Any] = {
        "TimePeriod": {
            "Start": today.replace(day=1).isoformat(),
            "End": (today + timedelta(days=1)).isoformat(),
        },
        "Granularity": "MONTHLY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
    }
    totals = dict.fromkeys(SERVICES, 0.0)
    client = _client()
    for _ in range(PAGE_BUDGET):
        response = client.get_cost_and_usage(**request)
        for period in response.get("ResultsByTime") or []:
            for group in period.get("Groups") or []:
                keys = group.get("Keys") or [""]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                totals[service_bucket(str(keys[0]))] += amount
        token = response.get("NextPageToken")
        if not token:
            return totals
        request["NextPageToken"] = token
    raise RuntimeError("cost explorer pages over budget")
