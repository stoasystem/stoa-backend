"""DynamoDB access patterns for the WeeklyReport entity."""
import base64
import json

from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, Key
from stoa.db.dynamodb import get_table


def put_report(item: dict) -> None:
    table = get_table()
    table.put_item(Item={"PK": f"REPORT#{item['report_id']}", "SK": "SUMMARY", **item})


def try_claim_report_generation(item: dict) -> bool:
    table = get_table()
    try:
        table.put_item(
            Item={"PK": f"REPORT#{item['report_id']}", "SK": "SUMMARY", **item},
            ConditionExpression="attribute_not_exists(PK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def update_report_status(report_id: str, status: str, **fields) -> None:
    table = get_table()
    update_fields = {"status": status, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    table.update_item(
        Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
        UpdateExpression="SET " + ", ".join(
            f"{name} = :v{index}" for index, name in enumerate(names)
        ),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def try_apply_report_edit(
    report_id: str,
    *,
    expected_updated_at: str | None,
    status: str,
    fields: dict,
) -> bool:
    table = get_table()
    update_fields = {"status": status, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    if expected_updated_at is None:
        condition = "attribute_not_exists(updated_at)"
    else:
        condition = "updated_at = :expected_updated_at"
        values[":expected_updated_at"] = expected_updated_at
    try:
        table.update_item(
            Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
            UpdateExpression="SET " + ", ".join(
                f"{name} = :v{index}" for index, name in enumerate(names)
            ),
            ConditionExpression=condition,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_report_edit_draft(report_id: str, draft: dict) -> None:
    table = get_table()
    table.put_item(
        Item={
            "PK": f"REPORT#{report_id}",
            "SK": f"EDIT_DRAFT#{draft['draft_id']}",
            "entity_type": "REPORT_EDIT_DRAFT",
            **draft,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def get_report_edit_draft(report_id: str, draft_id: str) -> dict | None:
    table = get_table()
    response = table.get_item(
        Key={"PK": f"REPORT#{report_id}", "SK": f"EDIT_DRAFT#{draft_id}"}
    )
    return response.get("Item")


def mark_report_edit_draft_applied(
    report_id: str,
    draft_id: str,
    *,
    applied_at: str,
    applied_by: str,
) -> bool:
    table = get_table()
    try:
        table.update_item(
            Key={"PK": f"REPORT#{report_id}", "SK": f"EDIT_DRAFT#{draft_id}"},
            UpdateExpression=(
                "SET #status = :applied, applied_at = :applied_at, "
                "applied_by = :applied_by, updated_at = :applied_at"
            ),
            ConditionExpression="#status = :draft",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":applied": "applied",
                ":draft": "draft",
                ":applied_at": applied_at,
                ":applied_by": applied_by,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_report_artifact_edit_draft(report_id: str, draft: dict) -> None:
    table = get_table()
    table.put_item(
        Item={
            "PK": f"REPORT#{report_id}",
            "SK": f"ARTIFACT_EDIT_DRAFT#{draft['draft_id']}",
            "entity_type": "REPORT_ARTIFACT_EDIT_DRAFT",
            **draft,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def get_report_artifact_edit_draft(report_id: str, draft_id: str) -> dict | None:
    table = get_table()
    response = table.get_item(
        Key={"PK": f"REPORT#{report_id}", "SK": f"ARTIFACT_EDIT_DRAFT#{draft_id}"}
    )
    return response.get("Item")


def mark_report_artifact_edit_draft_applied(
    report_id: str,
    draft_id: str,
    *,
    applied_at: str,
    applied_by: str,
    artifact_version_id: str,
) -> bool:
    table = get_table()
    try:
        table.update_item(
            Key={"PK": f"REPORT#{report_id}", "SK": f"ARTIFACT_EDIT_DRAFT#{draft_id}"},
            UpdateExpression=(
                "SET #status = :applied, applied_at = :applied_at, "
                "applied_by = :applied_by, artifact_version_id = :artifact_version_id, "
                "updated_at = :applied_at"
            ),
            ConditionExpression="#status = :draft",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":applied": "applied",
                ":draft": "draft",
                ":applied_at": applied_at,
                ":applied_by": applied_by,
                ":artifact_version_id": artifact_version_id,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_report_artifact_rollback_preview(report_id: str, preview: dict) -> None:
    table = get_table()
    table.put_item(
        Item={
            "PK": f"REPORT#{report_id}",
            "SK": f"ARTIFACT_ROLLBACK_PREVIEW#{preview['preview_id']}",
            "entity_type": "REPORT_ARTIFACT_ROLLBACK_PREVIEW",
            **preview,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def get_report_artifact_rollback_preview(report_id: str, preview_id: str) -> dict | None:
    table = get_table()
    response = table.get_item(
        Key={"PK": f"REPORT#{report_id}", "SK": f"ARTIFACT_ROLLBACK_PREVIEW#{preview_id}"}
    )
    return response.get("Item")


def mark_report_artifact_rollback_preview_applied(
    report_id: str,
    preview_id: str,
    *,
    applied_at: str,
    applied_by: str,
    artifact_version_id: str | None,
) -> bool:
    table = get_table()
    values = {
        ":applied": "applied",
        ":draft": "draft",
        ":applied_at": applied_at,
        ":applied_by": applied_by,
    }
    update_expression = (
        "SET #status = :applied, applied_at = :applied_at, "
        "applied_by = :applied_by, updated_at = :applied_at"
    )
    if artifact_version_id is not None:
        update_expression += ", artifact_version_id = :artifact_version_id"
        values[":artifact_version_id"] = artifact_version_id
    try:
        table.update_item(
            Key={"PK": f"REPORT#{report_id}", "SK": f"ARTIFACT_ROLLBACK_PREVIEW#{preview_id}"},
            UpdateExpression=update_expression,
            ConditionExpression="#status = :draft",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def try_apply_report_artifact_edit(
    report_id: str,
    *,
    expected_updated_at: str | None,
    expected_artifact_version_id: str | None,
    expected_json_s3_key: str | None,
    expected_html_s3_key: str | None,
    status: str,
    fields: dict,
) -> bool:
    table = get_table()
    update_fields = {"status": status, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    conditions = []
    if expected_updated_at is None:
        conditions.append("attribute_not_exists(updated_at)")
    else:
        conditions.append("updated_at = :expected_updated_at")
        values[":expected_updated_at"] = expected_updated_at
    if expected_artifact_version_id is None:
        conditions.append("attribute_not_exists(artifact_version_id)")
    else:
        conditions.append("artifact_version_id = :expected_artifact_version_id")
        values[":expected_artifact_version_id"] = expected_artifact_version_id
    if expected_json_s3_key is not None:
        conditions.append("json_s3_key = :expected_json_s3_key")
        values[":expected_json_s3_key"] = expected_json_s3_key
    if expected_html_s3_key is not None:
        conditions.append("html_s3_key = :expected_html_s3_key")
        values[":expected_html_s3_key"] = expected_html_s3_key
    try:
        table.update_item(
            Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
            UpdateExpression="SET " + ", ".join(
                f"{name} = :v{index}" for index, name in enumerate(names)
            ),
            ConditionExpression=" AND ".join(conditions),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def put_report_audit_event(report_id: str, event: dict) -> None:
    """Append one immutable report audit event."""
    table = get_table()
    table.put_item(
        Item={
            "PK": f"REPORT#{report_id}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "REPORT_AUDIT_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_recovery_job_audit_event(job_id: str, event: dict) -> None:
    """Append one immutable recovery job audit event."""
    table = get_table()
    table.put_item(
        Item={
            "PK": f"REPORT_RECOVERY_JOB#{job_id}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "REPORT_RECOVERY_JOB_AUDIT_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_support_handoff_audit_event(package_id: str, event: dict) -> None:
    """Append one immutable support handoff audit event."""
    table = get_table()
    table.put_item(
        Item={
            "PK": f"SUPPORT_HANDOFF#{package_id}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "SUPPORT_HANDOFF_AUDIT_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_audit_retention_audit_event(manifest_id: str, event: dict) -> None:
    """Append one metadata-only audit retention event."""
    table = get_table()
    table.put_item(
        Item={
            "PK": f"AUDIT_RETENTION#{manifest_id}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "AUDIT_RETENTION_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_audit_retention_manifest(manifest_id: str, manifest: dict) -> bool:
    """Persist one immutable-evidence manifest reference without overwriting."""
    table = get_table()
    try:
        table.put_item(
            Item={
                "PK": f"AUDIT_RETENTION#{manifest_id}",
                "SK": "IMMUTABLE_MANIFEST",
                "entity_type": "AUDIT_RETENTION_IMMUTABLE_MANIFEST",
                **manifest,
            },
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_audit_retention_manifest(manifest_id: str) -> dict | None:
    """Read one persisted immutable-evidence manifest reference."""
    response = get_table().get_item(
        Key={"PK": f"AUDIT_RETENTION#{manifest_id}", "SK": "IMMUTABLE_MANIFEST"}
    )
    return response.get("Item")


def put_legal_hold_metadata(scope_key: str, hold: dict) -> None:
    """Store current metadata-only legal hold state for an evidence scope."""
    get_table().put_item(
        Item={
            "PK": f"LEGAL_HOLD#{scope_key}",
            "SK": "SUMMARY",
            "entity_type": "LEGAL_HOLD_METADATA",
            **hold,
        },
    )


def get_legal_hold_metadata(scope_key: str) -> dict | None:
    """Read current metadata-only legal hold state for an evidence scope."""
    response = get_table().get_item(
        Key={"PK": f"LEGAL_HOLD#{scope_key}", "SK": "SUMMARY"}
    )
    return response.get("Item")


def put_legal_hold_audit_event(scope_key: str, event: dict) -> None:
    """Append one metadata-only legal hold audit event."""
    get_table().put_item(
        Item={
            "PK": f"LEGAL_HOLD#{scope_key}",
            "SK": f"AUDIT#{event['event_at']}#{event['event_id']}",
            "entity_type": "LEGAL_HOLD_AUDIT_EVENT",
            **event,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )


def put_recovery_job(job: dict, targets: list[dict]) -> None:
    """Persist one recovery job and its stable target snapshot."""
    table = get_table()
    table.put_item(
        Item={
            "PK": f"REPORT_RECOVERY_JOB#{job['job_id']}",
            "SK": "SUMMARY",
            "entity_type": "REPORT_RECOVERY_JOB",
            **job,
        },
        ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
    )
    for index, target in enumerate(targets):
        table.put_item(
            Item={
                "PK": f"REPORT_RECOVERY_JOB#{job['job_id']}",
                "SK": f"TARGET#{index:05d}#{target['target_id']}",
                "entity_type": "REPORT_RECOVERY_JOB_TARGET",
                "job_id": job["job_id"],
                "target_index": index,
                **target,
            },
            ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
        )


def get_recovery_job(job_id: str) -> dict | None:
    table = get_table()
    response = table.get_item(Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": "SUMMARY"})
    return response.get("Item")


def list_recovery_jobs(*, limit: int = 50, last_key: dict | None = None) -> dict:
    table = get_table()
    kwargs = {
        "FilterExpression": Attr("PK").begins_with("REPORT_RECOVERY_JOB#") & Attr("SK").eq("SUMMARY"),
        "Limit": limit,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.scan(**kwargs)


def list_recovery_job_targets(job_id: str, *, limit: int = 50, last_key: dict | None = None) -> dict:
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"REPORT_RECOVERY_JOB#{job_id}") & Key("SK").begins_with("TARGET#"),
        "Limit": limit,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)


def try_claim_recovery_job(job_id: str, *, started_at: str) -> bool:
    table = get_table()
    try:
        table.update_item(
            Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": "SUMMARY"},
            UpdateExpression="SET #status = :running, started_at = if_not_exists(started_at, :started_at), updated_at = :started_at",
            ConditionExpression="#status = :queued",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":running": "running",
                ":queued": "queued",
                ":started_at": started_at,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def request_recovery_job_cancellation(job_id: str, *, requested_by: str, requested_at: str) -> bool:
    table = get_table()
    try:
        table.update_item(
            Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": "SUMMARY"},
            UpdateExpression=(
                "SET #status = :cancellation_requested, "
                "cancellation_requested_by = :requested_by, "
                "cancellation_requested_at = :requested_at, "
                "updated_at = :requested_at"
            ),
            ConditionExpression="#status IN (:queued, :running)",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":cancellation_requested": "cancellation_requested",
                ":queued": "queued",
                ":running": "running",
                ":requested_by": requested_by,
                ":requested_at": requested_at,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def update_recovery_job_status(job_id: str, status: str, **fields) -> None:
    table = get_table()
    update_fields = {"status": status, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    table.update_item(
        Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": "SUMMARY"},
        UpdateExpression="SET " + ", ".join(
            f"{name} = :v{index}" for index, name in enumerate(names)
        ),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def try_claim_recovery_job_target(job_id: str, target_sk: str, *, attempted_at: str) -> bool:
    table = get_table()
    try:
        table.update_item(
            Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": target_sk},
            UpdateExpression="SET #result = :in_progress, attempted_at = :attempted_at, updated_at = :attempted_at",
            ConditionExpression="#result = :pending",
            ExpressionAttributeNames={"#result": "result"},
            ExpressionAttributeValues={
                ":in_progress": "in_progress",
                ":pending": "pending",
                ":attempted_at": attempted_at,
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def update_recovery_job_target(job_id: str, target_sk: str, result: str, **fields) -> None:
    table = get_table()
    update_fields = {"result": result, **fields}
    names = {f"#f{index}": key for index, key in enumerate(update_fields)}
    values = {f":v{index}": value for index, value in enumerate(update_fields.values())}
    table.update_item(
        Key={"PK": f"REPORT_RECOVERY_JOB#{job_id}", "SK": target_sk},
        UpdateExpression="SET " + ", ".join(
            f"{name} = :v{index}" for index, name in enumerate(names)
        ),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def list_report_audit_events(
    report_id: str,
    *,
    limit: int = 50,
    last_key: dict | None = None,
) -> dict:
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"REPORT#{report_id}") & Key("SK").begins_with("AUDIT#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)


def list_recovery_job_audit_events(
    job_id: str,
    *,
    limit: int = 50,
    last_key: dict | None = None,
) -> dict:
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"REPORT_RECOVERY_JOB#{job_id}")
        & Key("SK").begins_with("AUDIT#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)


def list_support_handoff_audit_events(
    package_id: str,
    *,
    limit: int = 50,
    last_key: dict | None = None,
) -> dict:
    table = get_table()
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"SUPPORT_HANDOFF#{package_id}")
        & Key("SK").begins_with("AUDIT#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)


def try_start_generation_retry(report_id: str, *, operator: str, attempted_at: str) -> bool:
    """Atomically claim a generation-failed report for one admin retry."""
    table = get_table()
    try:
        table.update_item(
            Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
            UpdateExpression=(
                "SET #status = :retrying, "
                "generation_retry_attempted_at = :attempted_at, "
                "last_operation = :operation, "
                "last_operation_at = :attempted_at, "
                "last_operation_by = :operator, "
                "last_operation_result = :in_progress, "
                "updated_at = :attempted_at"
            ),
            ConditionExpression="#status = :expected",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":retrying": "generation_retrying",
                ":expected": "generation_failed",
                ":attempted_at": attempted_at,
                ":operation": "retry_generation",
                ":operator": operator,
                ":in_progress": "in_progress",
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def try_claim_report_resend(report_id: str, *, operator: str, attempted_at: str) -> bool:
    """Atomically claim a failed email report before resend side effects."""
    table = get_table()
    try:
        table.update_item(
            Key={"PK": f"REPORT#{report_id}", "SK": "SUMMARY"},
            UpdateExpression=(
                "SET #status = :resending, "
                "resend_attempted_at = :attempted_at, "
                "last_operation = :operation, "
                "last_operation_at = :attempted_at, "
                "last_operation_by = :operator, "
                "last_operation_result = :in_progress, "
                "updated_at = :attempted_at"
            ),
            ConditionExpression="#status = :email_failed OR email_status = :failed",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":resending": "email_resending",
                ":email_failed": "email_failed",
                ":failed": "failed",
                ":attempted_at": attempted_at,
                ":operation": "resend_email",
                ":operator": operator,
                ":in_progress": "in_progress",
            },
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise
    return True


def get_report_by_week(parent_id: str, week_start: str) -> dict | None:
    table = get_table()
    resp = table.query(
        IndexName="GSI-ParentId",
        KeyConditionExpression=Key("parent_id").eq(parent_id) & Key("week_start").eq(week_start),
        Limit=1,
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def get_report_for_child_by_week(parent_id: str, student_id: str, week_start: str) -> dict | None:
    last_key = None
    while True:
        result = list_reports_for_parent_week(parent_id, week_start, last_key=last_key)
        for item in result.get("Items", []):
            if item.get("SK") == "SUMMARY" and item.get("student_id") == student_id:
                return item
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            return None


def encode_page_token(last_key: dict | None) -> str | None:
    """Encode a DynamoDB LastEvaluatedKey as an opaque API token."""
    if not last_key:
        return None
    raw = json.dumps(last_key, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_page_token(token: str | None) -> dict | None:
    """Decode an opaque API token into a DynamoDB ExclusiveStartKey."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        decoded = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination token") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Invalid pagination token")
    if not _is_valid_report_page_key(decoded):
        raise ValueError("Invalid pagination token")
    return decoded


def encode_admin_page_token(last_key: dict | None) -> str | None:
    """Encode an admin report-ops page token.

    Cross-parent admin listing uses DynamoDB Scan with a FilterExpression. Scan
    pagination keys can point at any item in the single-table design, not only
    report summary rows. Keep normal report page tokens strict, but allow admin
    report ops to round-trip the scan key it received from DynamoDB.
    """
    if not last_key:
        return None
    raw = json.dumps(
        {"scope": "admin_reports", "key": last_key},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_admin_page_token(token: str | None) -> dict | None:
    """Decode an admin report-ops page token into an ExclusiveStartKey."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        decoded = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination token") from exc
    if _is_valid_admin_page_payload(decoded):
        return decoded["key"]
    # Backward compatibility for older admin report tokens that encoded the
    # report LastEvaluatedKey directly.
    if isinstance(decoded, dict) and _is_valid_report_page_key(decoded):
        return decoded
    raise ValueError("Invalid pagination token")


def encode_audit_page_token(last_key: dict | None) -> str | None:
    """Encode an audit timeline page token."""
    if not last_key:
        return None
    raw = json.dumps(
        {"scope": "report_audit", "key": last_key},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_audit_page_token(token: str | None) -> dict | None:
    """Decode an audit timeline page token into an ExclusiveStartKey."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        decoded = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination token") from exc
    if _is_valid_audit_page_payload(decoded):
        return decoded["key"]
    raise ValueError("Invalid pagination token")


def encode_recovery_job_page_token(last_key: dict | None) -> str | None:
    """Encode recovery job list/result pagination keys."""
    if not last_key:
        return None
    raw = json.dumps(
        {"scope": "recovery_jobs", "key": last_key},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_recovery_job_page_token(token: str | None) -> dict | None:
    """Decode recovery job pagination token into an ExclusiveStartKey."""
    if not token:
        return None
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        decoded = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pagination token") from exc
    if _is_valid_recovery_job_page_payload(decoded):
        return decoded["key"]
    raise ValueError("Invalid pagination token")


def list_reports_for_admin(
    *,
    status: str | None = None,
    week_start: str | None = None,
    parent_id: str | None = None,
    student_id: str | None = None,
    limit: int = 50,
    last_key: dict | None = None,
) -> dict:
    """List report summary rows for admin operations.

    Parent-filtered access uses the existing parent/week GSI where possible.
    Cross-parent admin access uses a bounded scan for pilot volume; callers must
    pass a strict limit and preserve LastEvaluatedKey pagination.
    """
    if parent_id:
        return _list_reports_for_admin_parent_query(
            parent_id=parent_id,
            status=status,
            week_start=week_start,
            student_id=student_id,
            limit=limit,
            last_key=last_key,
        )
    return _list_reports_for_admin_scan(
        status=status,
        week_start=week_start,
        student_id=student_id,
        limit=limit,
        last_key=last_key,
    )


def _list_reports_for_admin_parent_query(
    *,
    parent_id: str,
    status: str | None,
    week_start: str | None,
    student_id: str | None,
    limit: int,
    last_key: dict | None,
) -> dict:
    table = get_table()
    key_expr = Key("parent_id").eq(parent_id)
    if week_start:
        key_expr = key_expr & Key("week_start").eq(week_start)

    kwargs = {
        "IndexName": "GSI-ParentId",
        "KeyConditionExpression": key_expr,
        "Limit": limit,
        "ScanIndexForward": False,
    }
    filter_expr = _admin_report_filter_expression(status=status, student_id=student_id)
    if filter_expr is not None:
        kwargs["FilterExpression"] = filter_expr
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)


def _list_reports_for_admin_scan(
    *,
    status: str | None,
    week_start: str | None,
    student_id: str | None,
    limit: int,
    last_key: dict | None,
) -> dict:
    table = get_table()
    filter_expr = Attr("PK").begins_with("REPORT#") & Attr("SK").eq("SUMMARY")
    extra_filter = _admin_report_filter_expression(
        status=status,
        week_start=week_start,
        student_id=student_id,
    )
    if extra_filter is not None:
        filter_expr = filter_expr & extra_filter
    kwargs = {
        "FilterExpression": filter_expr,
        "Limit": limit,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.scan(**kwargs)


def _admin_report_filter_expression(
    *,
    status: str | None = None,
    week_start: str | None = None,
    student_id: str | None = None,
):
    filter_expr = None
    if status:
        filter_expr = Attr("status").eq(status)
    if week_start:
        week_filter = Attr("week_start").eq(week_start)
        filter_expr = week_filter if filter_expr is None else filter_expr & week_filter
    if student_id:
        student_filter = Attr("student_id").eq(student_id)
        filter_expr = student_filter if filter_expr is None else filter_expr & student_filter
    return filter_expr


def _is_valid_report_page_key(decoded: dict) -> bool:
    pk = decoded.get("PK")
    sk = decoded.get("SK")
    return (
        isinstance(pk, str)
        and pk.startswith("REPORT#")
        and isinstance(sk, str)
        and sk == "SUMMARY"
    )


def _is_valid_admin_page_payload(decoded: object) -> bool:
    if not isinstance(decoded, dict) or decoded.get("scope") != "admin_reports":
        return False
    key = decoded.get("key")
    if not isinstance(key, dict):
        return False
    pk = key.get("PK")
    sk = key.get("SK")
    return isinstance(pk, str) and isinstance(sk, str)


def _is_valid_audit_page_payload(decoded: object) -> bool:
    if not isinstance(decoded, dict) or decoded.get("scope") != "report_audit":
        return False
    key = decoded.get("key")
    if not isinstance(key, dict):
        return False
    pk = key.get("PK")
    sk = key.get("SK")
    return (
        isinstance(pk, str)
        and (
            pk.startswith("REPORT#")
            or pk.startswith("REPORT_RECOVERY_JOB#")
        )
        and isinstance(sk, str)
        and sk.startswith("AUDIT#")
    )


def _is_valid_recovery_job_page_payload(decoded: object) -> bool:
    if not isinstance(decoded, dict) or decoded.get("scope") != "recovery_jobs":
        return False
    key = decoded.get("key")
    if not isinstance(key, dict):
        return False
    pk = key.get("PK")
    sk = key.get("SK")
    return isinstance(pk, str) and pk.startswith("REPORT_RECOVERY_JOB#") and isinstance(sk, str)


def list_reports_for_parent_week(
    parent_id: str,
    week_start: str,
    last_key: dict | None = None,
) -> dict:
    table = get_table()
    kwargs = {
        "IndexName": "GSI-ParentId",
        "KeyConditionExpression": Key("parent_id").eq(parent_id) & Key("week_start").eq(week_start),
        "FilterExpression": Attr("SK").eq("SUMMARY"),
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)


def list_reports_for_parent(
    parent_id: str,
    limit: int = 25,
    last_key: dict | None = None,
) -> dict:
    table = get_table()
    kwargs = {
        "IndexName": "GSI-ParentId",
        "KeyConditionExpression": Key("parent_id").eq(parent_id),
        "FilterExpression": Attr("SK").eq("SUMMARY"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return table.query(**kwargs)
