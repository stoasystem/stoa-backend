import json
from datetime import date

import pytest

from stoa.services import report_artifact_service


class FakeBody:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return self.payload


class FakeS3Client:
    def __init__(self, read_body=None, fail_put_key=None, fail_delete=False):
        self.puts = []
        self.gets = []
        self.deletes = []
        self.read_body = read_body
        self.objects = {}
        self.fail_put_key = fail_put_key
        self.fail_delete = fail_delete

    def put_object(self, **kwargs):
        if kwargs["Key"] == self.fail_put_key:
            raise RuntimeError("put failed")
        self.puts.append(kwargs)
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        self.gets.append(kwargs)
        return {"Body": FakeBody(self.read_body if self.read_body is not None else self.objects[kwargs["Key"]])}

    def delete_object(self, **kwargs):
        if self.fail_delete:
            raise RuntimeError("delete failed")
        self.deletes.append(kwargs)
        self.objects.pop(kwargs["Key"], None)


def test_build_report_artifact_keys_uses_exact_canonical_shape():
    keys = report_artifact_service.build_report_artifact_keys(
        "parent-1",
        "student_1",
        date(2026, 6, 1),
    )

    assert keys.json_key == "weekly-reports/parent-1/student_1/2026-06-01/report.json"
    assert keys.html_key == "weekly-reports/parent-1/student_1/2026-06-01/report.html"


@pytest.mark.parametrize(
    ("parent_id", "student_id", "week_start"),
    [
        ("", "student-1", "2026-06-01"),
        ("parent-1", "", "2026-06-01"),
        ("parent@example.com", "student-1", "2026-06-01"),
        ("Parent One", "student-1", "2026-06-01"),
        ("parent/1", "student-1", "2026-06-01"),
        ("parent-1", "student@example.com", "2026-06-01"),
        ("parent-1", "Student One", "2026-06-01"),
        ("parent-1", "student/1", "2026-06-01"),
        ("parent-1", "student-1", ""),
        ("parent-1", "student-1", "not-a-date"),
    ],
)
def test_build_report_artifact_keys_rejects_unsafe_or_blank_inputs(
    parent_id,
    student_id,
    week_start,
):
    with pytest.raises(ValueError):
        report_artifact_service.build_report_artifact_keys(parent_id, student_id, week_start)


def test_write_report_artifacts_uses_private_bucket_content_types_and_no_acl(monkeypatch):
    monkeypatch.setattr(report_artifact_service.settings, "s3_reports_bucket", "reports-bucket")
    keys = report_artifact_service.build_report_artifact_keys(
        "parent-1",
        "student-1",
        "2026-06-01",
    )
    s3 = FakeS3Client()

    report_artifact_service.write_report_artifacts(
        keys,
        {"report": {"id": "report-1"}},
        "<html>Report</html>",
        s3_client=s3,
    )

    assert [put["Key"] for put in s3.puts] == [keys.json_key, keys.html_key]
    assert [put["Bucket"] for put in s3.puts] == ["reports-bucket", "reports-bucket"]
    assert s3.puts[0]["ContentType"] == report_artifact_service.REPORT_JSON_CONTENT_TYPE
    assert s3.puts[1]["ContentType"] == report_artifact_service.REPORT_HTML_CONTENT_TYPE
    assert json.loads(s3.puts[0]["Body"].decode()) == {"report": {"id": "report-1"}}
    assert s3.puts[1]["Body"] == b"<html>Report</html>"
    assert "ACL" not in s3.puts[0]
    assert "ACL" not in s3.puts[1]
    assert s3.deletes == []


def test_write_report_artifacts_cleans_json_partial_when_html_write_fails(monkeypatch):
    monkeypatch.setattr(report_artifact_service.settings, "s3_reports_bucket", "reports-bucket")
    keys = report_artifact_service.build_report_artifact_keys(
        "parent-1",
        "student-1",
        "2026-06-01",
    )
    s3 = FakeS3Client(fail_put_key=keys.html_key)

    with pytest.raises(RuntimeError, match="put failed"):
        report_artifact_service.write_report_artifacts(
            keys,
            {"report": {"id": "report-1"}},
            "<html>Report</html>",
            s3_client=s3,
        )

    assert [put["Key"] for put in s3.puts] == [keys.json_key]
    assert s3.deletes == [{"Bucket": "reports-bucket", "Key": keys.json_key}]
    assert keys.json_key not in s3.objects


def test_write_report_artifacts_preserves_html_failure_when_partial_cleanup_fails(monkeypatch):
    monkeypatch.setattr(report_artifact_service.settings, "s3_reports_bucket", "reports-bucket")
    keys = report_artifact_service.build_report_artifact_keys(
        "parent-1",
        "student-1",
        "2026-06-01",
    )
    s3 = FakeS3Client(fail_put_key=keys.html_key, fail_delete=True)

    with pytest.raises(RuntimeError, match="put failed"):
        report_artifact_service.write_report_artifacts(
            keys,
            {"report": {"id": "report-1"}},
            "<html>Report</html>",
            s3_client=s3,
        )

    assert [put["Key"] for put in s3.puts] == [keys.json_key]


def test_get_report_json_reads_and_decodes_private_artifact(monkeypatch):
    monkeypatch.setattr(report_artifact_service.settings, "s3_reports_bucket", "reports-bucket")
    s3 = FakeS3Client(read_body=b'{"report":{"id":"report-1"}}')

    artifact = report_artifact_service.get_report_json(
        "weekly-reports/parent-1/student-1/2026-06-01/report.json",
        s3_client=s3,
    )

    assert artifact == {"report": {"id": "report-1"}}
    assert s3.gets == [
        {
            "Bucket": "reports-bucket",
            "Key": "weekly-reports/parent-1/student-1/2026-06-01/report.json",
        }
    ]


def test_get_report_json_rejects_noncanonical_keys():
    with pytest.raises(ValueError, match="canonical"):
        report_artifact_service.get_report_json("reports/parent-1/student-1/2026-06-01/report.json")


def test_run_report_artifact_s3_smoke_writes_and_reads_private_json(monkeypatch):
    monkeypatch.setattr(report_artifact_service.settings, "s3_reports_bucket", "reports-bucket")
    s3 = FakeS3Client()

    result = report_artifact_service.run_report_artifact_s3_smoke(
        {"week_start": "2026-06-01"},
        s3_client=s3,
    )

    expected_key = "weekly-reports/smoke-parent/smoke-student/2026-06-01/report.json"
    assert result == {
        "status": "passed",
        "bucket": "reports-bucket",
        "key": expected_key,
        "content_type": "application/json",
        "readback_ok": True,
        "cleanup": "performed",
    }
    assert len(s3.puts) == 1
    assert s3.puts[0]["Bucket"] == "reports-bucket"
    assert s3.puts[0]["Key"] == expected_key
    assert s3.puts[0]["ContentType"] == "application/json"
    assert "ACL" not in s3.puts[0]
    assert s3.gets == [{"Bucket": "reports-bucket", "Key": expected_key}]
    assert s3.deletes == [{"Bucket": "reports-bucket", "Key": expected_key}]
    assert expected_key not in s3.objects
    assert "content" not in result
    assert "publicUrl" not in result
    assert "presignedUrl" not in result


def test_run_report_artifact_s3_smoke_reports_cleanup_failure(monkeypatch):
    monkeypatch.setattr(report_artifact_service.settings, "s3_reports_bucket", "reports-bucket")
    s3 = FakeS3Client(fail_delete=True)

    result = report_artifact_service.run_report_artifact_s3_smoke(
        {"week_start": "2026-06-01"},
        s3_client=s3,
    )

    assert result["status"] == "failed"
    assert result["readback_ok"] is True
    assert result["cleanup"] == "failed"
    assert result["cleanup_error_class"] == "RuntimeError"
