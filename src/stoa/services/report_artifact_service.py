"""Private S3 artifact helpers for weekly reports."""

from dataclasses import dataclass
from datetime import date
import json
import re
from typing import Any

import boto3

from stoa.config import settings

REPORT_ARTIFACT_PREFIX = "weekly-reports"
REPORT_JSON_CONTENT_TYPE = "application/json"
REPORT_HTML_CONTENT_TYPE = "text/html; charset=utf-8"

_BACKEND_ID_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.=-]+$")


@dataclass(frozen=True)
class ReportArtifactKeys:
    json_key: str
    html_key: str


def build_report_artifact_keys(
    parent_id: str,
    student_id: str,
    week_start: str | date,
) -> ReportArtifactKeys:
    """Build canonical private S3 keys for a weekly report's artifacts."""
    parent_segment = _validate_backend_id_segment(parent_id, "parent_id")
    student_segment = _validate_backend_id_segment(student_id, "student_id")
    week_segment = _validate_week_start(week_start)
    prefix = f"{REPORT_ARTIFACT_PREFIX}/{parent_segment}/{student_segment}/{week_segment}"
    return ReportArtifactKeys(
        json_key=f"{prefix}/report.json",
        html_key=f"{prefix}/report.html",
    )


def write_report_artifacts(
    keys: ReportArtifactKeys,
    json_artifact: dict[str, Any],
    html_artifact: str,
    *,
    s3_client: Any | None = None,
) -> None:
    """Write JSON then HTML report artifacts to the private reports bucket."""
    s3 = s3_client or boto3.client("s3", region_name=settings.aws_region)
    bucket = settings.report_artifacts_bucket
    s3.put_object(
        Bucket=bucket,
        Key=keys.json_key,
        Body=json.dumps(json_artifact, separators=(",", ":"), ensure_ascii=False).encode(),
        ContentType=REPORT_JSON_CONTENT_TYPE,
    )
    s3.put_object(
        Bucket=bucket,
        Key=keys.html_key,
        Body=html_artifact.encode(),
        ContentType=REPORT_HTML_CONTENT_TYPE,
    )


def get_report_json(s3_key: str, *, s3_client: Any | None = None) -> dict[str, Any]:
    """Read and decode a JSON report artifact from the private reports bucket."""
    key = _validate_json_artifact_key(s3_key)
    s3 = s3_client or boto3.client("s3", region_name=settings.aws_region)
    response = s3.get_object(Bucket=settings.report_artifacts_bucket, Key=key)
    body = response["Body"].read()
    if isinstance(body, bytes):
        body = body.decode()
    artifact = json.loads(body)
    if not isinstance(artifact, dict):
        raise ValueError("report JSON artifact must decode to an object")
    return artifact


def _validate_backend_id_segment(value: str, field_name: str) -> str:
    segment = str(value or "").strip()
    if not segment:
        raise ValueError(f"{field_name} is required for report artifact key")
    if not _BACKEND_ID_SEGMENT_RE.fullmatch(segment):
        raise ValueError(f"{field_name} must be a canonical backend identifier")
    return segment


def _validate_week_start(value: str | date) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("week_start is required for report artifact key")
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ValueError("week_start must be an ISO date") from exc


def _validate_json_artifact_key(value: str) -> str:
    key = str(value or "").strip()
    if not key:
        raise ValueError("s3_key is required")
    if not key.startswith(f"{REPORT_ARTIFACT_PREFIX}/") or not key.endswith("/report.json"):
        raise ValueError("s3_key must be a canonical report JSON artifact key")
    return key
