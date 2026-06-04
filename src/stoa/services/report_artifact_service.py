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
REPORT_ARTIFACT_SMOKE_MARKER = "report-artifact-s3-smoke"
REPORT_ARTIFACT_SMOKE_PARENT_ID = "smoke-parent"
REPORT_ARTIFACT_SMOKE_STUDENT_ID = "smoke-student"
REPORT_ARTIFACT_SMOKE_WEEK_START = "2026-06-01"

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
    try:
        s3.put_object(
            Bucket=bucket,
            Key=keys.html_key,
            Body=html_artifact.encode(),
            ContentType=REPORT_HTML_CONTENT_TYPE,
        )
    except Exception:
        try:
            _delete_report_artifact(bucket, keys.json_key, s3_client=s3)
        except Exception:
            pass
        raise


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


def get_report_html(s3_key: str, *, s3_client: Any | None = None) -> str:
    """Read and decode an HTML report artifact from the private reports bucket."""
    key = _validate_html_artifact_key(s3_key)
    s3 = s3_client or boto3.client("s3", region_name=settings.aws_region)
    response = s3.get_object(Bucket=settings.report_artifacts_bucket, Key=key)
    body = response["Body"].read()
    if isinstance(body, bytes):
        return body.decode()
    return str(body)


def run_report_artifact_s3_smoke(
    event: dict[str, Any] | None = None,
    *,
    s3_client: Any | None = None,
) -> dict[str, Any]:
    """Write and read a deterministic private JSON artifact for Lambda smoke verification."""
    event = event or {}
    week_start = event.get("week_start") or event.get("weekStart") or REPORT_ARTIFACT_SMOKE_WEEK_START
    keys = build_report_artifact_keys(
        event.get("parent_id") or REPORT_ARTIFACT_SMOKE_PARENT_ID,
        event.get("student_id") or REPORT_ARTIFACT_SMOKE_STUDENT_ID,
        week_start,
    )
    bucket = settings.report_artifacts_bucket
    s3 = s3_client or boto3.client("s3", region_name=settings.aws_region)
    body = {
        "marker": REPORT_ARTIFACT_SMOKE_MARKER,
        "key": keys.json_key,
        "weekStart": _validate_week_start(week_start),
    }

    s3.put_object(
        Bucket=bucket,
        Key=keys.json_key,
        Body=json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(),
        ContentType=REPORT_JSON_CONTENT_TYPE,
    )
    readback = get_report_json(keys.json_key, s3_client=s3)
    readback_ok = (
        readback.get("marker") == REPORT_ARTIFACT_SMOKE_MARKER
        and readback.get("key") == keys.json_key
    )
    cleanup = "not_attempted"
    cleanup_error_class = None
    if readback_ok:
        try:
            _delete_report_artifact(bucket, keys.json_key, s3_client=s3)
            cleanup = "performed"
        except Exception as exc:
            cleanup = "failed"
            cleanup_error_class = type(exc).__name__
    status = "passed" if readback_ok and cleanup == "performed" else "failed"
    result = {
        "status": status,
        "bucket": bucket,
        "key": keys.json_key,
        "content_type": REPORT_JSON_CONTENT_TYPE,
        "readback_ok": readback_ok,
        "cleanup": cleanup,
    }
    if cleanup_error_class:
        result["cleanup_error_class"] = cleanup_error_class
    return result


def _delete_report_artifact(
    bucket: str,
    key: str,
    *,
    s3_client: Any,
) -> None:
    s3_client.delete_object(Bucket=bucket, Key=key)


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


def _validate_html_artifact_key(value: str) -> str:
    key = str(value or "").strip()
    if not key:
        raise ValueError("s3_key is required")
    if not key.startswith(f"{REPORT_ARTIFACT_PREFIX}/") or not key.endswith("/report.html"):
        raise ValueError("s3_key must be a canonical report HTML artifact key")
    return key
