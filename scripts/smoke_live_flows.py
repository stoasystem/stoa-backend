#!/usr/bin/env python3
"""Prove the core journeys work against a running environment.

The pytest suite is hermetic: a session fixture disables sockets for the whole
lifecycle and every repository and provider is replaced by a fake. That proves
function logic, not that an endpoint answers. This script closes the gap by
driving the real HTTP surface with the real identities.

Teacher and admin cannot use POST /auth/login: the public lane is restricted to
student and parent, so their tokens come from their own Cognito app clients.

Usage:
    export STOA_SMOKE_PASSWORD='...'
    python scripts/smoke_live_flows.py
    python scripts/smoke_live_flows.py --include-escalation
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BASE_URL = "https://api.stoaedu.ch"
REGION = "eu-central-2"

STUDENT_EMAIL = "student@test.stoaedu.ch"
PARENT_EMAIL = "parent@test.stoaedu.ch"
TEACHER_EMAIL = "teacher@test.stoaedu.ch"
ADMIN_EMAIL = "admin@test.stoaedu.ch"

TEACHER_CLIENT_ID = "7d30jdd64hkm26rda4hj0kgc4v"
ADMIN_CLIENT_ID = "2pdbv2evcivfoc6irkepip1ir0"


class SmokeFailure(Exception):
    """A check did not meet its expectation."""


@dataclass
class Report:
    passed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def check(self, name: str, fn) -> Any:
        try:
            value = fn()
        except SmokeFailure as exc:
            self.failed.append((name, str(exc)))
            print(f"  FAIL  {name}: {exc}", flush=True)
            return None
        except Exception as exc:  # noqa: BLE001 - the report must survive any failure
            self.failed.append((name, f"{type(exc).__name__}: {exc}"))
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        self.passed.append(name)
        print(f"  ok    {name}", flush=True)
        return value

    def skip(self, name: str, reason: str) -> None:
        self.skipped.append(name)
        print(f"  skip  {name} ({reason})", flush=True)


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
    expect: int | tuple[int, ...] = 200,
) -> Any:
    url = f"{base_url}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    expected = (expect,) if isinstance(expect, int) else expect
    try:
        with urllib.request.urlopen(req, timeout=40) as response:
            status = response.status
            payload = response.read().decode()
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = exc.read().decode()
    if status not in expected:
        raise SmokeFailure(f"{method} {path} returned {status}, expected {expected}: {payload[:200]}")
    try:
        return json.loads(payload) if payload else None
    except json.JSONDecodeError:
        return payload


def public_login(base_url: str, email: str, password: str, expected_role: str) -> str:
    data = request(base_url, "POST", "/auth/login", body={"email": email, "password": password})
    role = (data or {}).get("user", {}).get("role")
    if role != expected_role:
        raise SmokeFailure(f"{email} resolved role {role!r}, expected {expected_role!r}")
    token = (data or {}).get("accessToken")
    if not token:
        raise SmokeFailure(f"{email} login returned no access token")
    return token


def cognito_token(email: str, password: str, client_id: str) -> str:
    import boto3

    response = boto3.client("cognito-idp", region_name=REGION).initiate_auth(
        AuthFlow="USER_PASSWORD_AUTH",
        ClientId=client_id,
        AuthParameters={"USERNAME": email, "PASSWORD": password},
    )
    return response["AuthenticationResult"]["AccessToken"]


def privileged_login(base_url: str, email: str, password: str, client_id: str, expected_role: str) -> str:
    token = cognito_token(email, password, client_id)
    profile = request(base_url, "GET", "/auth/me", token=token)
    if (profile or {}).get("role") != expected_role:
        raise SmokeFailure(f"{email} resolved role {(profile or {}).get('role')!r}, expected {expected_role!r}")
    return token


# A one pixel PNG; the point is to exercise intent, chunk and complete, not the image.
PROBE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def upload_probe_image(base_url: str, token: str) -> dict:
    """Drive the three upload steps; each one failed independently in production."""
    intent = request(
        base_url, "POST", "/files/intents",
        token=token,
        body={
            "purpose": "conversation_attachment",
            "filename": "smoke-probe.png",
            "contentType": "image/png",
            "sizeBytes": len(PROBE_PNG),
        },
    )
    upload_id = intent["uploadId"]

    chunk = urllib.request.Request(
        f"{base_url}/files/{upload_id}/chunks/1", data=PROBE_PNG, method="PUT"
    )
    chunk.add_header("Content-Type", "application/octet-stream")
    chunk.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(chunk, timeout=40) as response:
            if response.status != 200:
                raise SmokeFailure(f"chunk upload returned {response.status}")
    except urllib.error.HTTPError as exc:
        raise SmokeFailure(f"chunk upload returned {exc.code}: {exc.read().decode()[:160]}") from None

    completed = request(
        base_url, "POST", f"/files/{upload_id}/complete", token=token, body={"partCount": 1}
    )
    if completed.get("status") != "validated":
        raise SmokeFailure(f"upload finished as {completed.get('status')}, expected validated")
    return completed


def report_week() -> str:
    """Weekly reports are keyed on the Monday that starts the week."""
    today = datetime.now(timezone.utc).date()
    return (today - timedelta(days=today.weekday())).isoformat()


class AllowanceExhausted(Exception):
    """The student has spent every teacher-support case this week."""


def escalate(base_url: str, student_token: str, conversation_id: str, marker: str) -> dict:
    try:
        return request(
            base_url,
            "POST",
            "/teacher-help/request",
            token=student_token,
            body={"conversationId": conversation_id, "message": f"smoke {marker}"},
        )
    except SmokeFailure as exc:
        if "teacher_support_allowance_exhausted" in str(exc):
            raise AllowanceExhausted from None
        raise


def await_queued(base_url: str, teacher_token: str, conversation_id: str) -> dict:
    """The teacher queue is a scan, so a fresh escalation needs a moment to appear."""
    for attempt in range(10):
        if attempt:
            time.sleep(3)
        items = request(
            base_url, "GET", "/teachers/me/help-requests", token=teacher_token
        ).get("items", [])
        for item in items:
            if item.get("conversationId") == conversation_id:
                return item
    raise SmokeFailure("request never appeared in the teacher queue")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("STOA_SMOKE_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument(
        "--include-escalation",
        action="store_true",
        help="Run the human-teacher journey; each run consumes one weekly teacher-support case.",
    )
    args = parser.parse_args()

    password = os.environ.get("STOA_SMOKE_PASSWORD", "").strip()
    if not password:
        print("ERROR: set STOA_SMOKE_PASSWORD before running", file=sys.stderr)
        return 2

    base = args.base_url.rstrip("/")
    report = Report()
    print(f"smoke target: {base}\n")

    print("service")
    report.check("health responds ok", lambda: (
        request(base, "GET", "/health")
        if request(base, "GET", "/health").get("status") == "ok"
        else (_ for _ in ()).throw(SmokeFailure("status is not ok"))
    ))

    print("\nidentity")
    student = report.check("student signs in", lambda: public_login(base, STUDENT_EMAIL, password, "student"))
    parent = report.check("parent signs in", lambda: public_login(base, PARENT_EMAIL, password, "parent"))
    teacher = report.check(
        "teacher signs in through its own client",
        lambda: privileged_login(base, TEACHER_EMAIL, password, TEACHER_CLIENT_ID, "teacher"),
    )
    report.check(
        "admin signs in through its own client",
        lambda: privileged_login(base, ADMIN_EMAIL, password, ADMIN_CLIENT_ID, "admin"),
    )

    print("\nstudent")
    if student:
        report.check("reads own profile", lambda: request(base, "GET", "/students/me/profile", token=student))
        report.check(
            "sees a teacher available",
            lambda: (
                request(base, "GET", "/teacher-help/availability", token=student)
                if request(base, "GET", "/teacher-help/availability", token=student).get("availableTeachers", 0) > 0
                else (_ for _ in ()).throw(SmokeFailure("no dispatchable teacher"))
            ),
        )
        conversation = report.check(
            "opens a conversation",
            lambda: request(
                base, "POST", "/conversations",
                token=student,
                body={"subject": "Mathematics", "grade": "9"},
                expect=201,
            ),
        )
    else:
        conversation = None
        report.skip("student journey", "sign-in failed")

    if student:
        report.check(
            "reads own learning history",
            lambda: (
                lambda seen: seen
                if isinstance(seen.get("items"), list)
                else (_ for _ in ()).throw(SmokeFailure("history did not return items"))
            )(request(base, "GET", "/students/me/learning-history", token=student)),
        )

    print("\nupload")
    if student:
        report.check("photographs an exercise end to end", lambda: upload_probe_image(base, student))
    else:
        report.skip("upload journey", "sign-in failed")

    print("\nparent")
    child = None
    if parent:
        children = report.check(
            "sees the linked child",
            lambda: (
                lambda seen: seen
                if seen.get("items")
                else (_ for _ in ()).throw(SmokeFailure("child list is empty"))
            )(request(base, "GET", "/parents/me/children", token=parent)),
        )
        child = (children or {}).get("items", [None])[0]
        report.check("reads its subscription", lambda: request(base, "GET", "/parents/me/subscription", token=parent))
    if parent and child:
        report.check(
            "reads the weekly report for its child",
            lambda: (
                lambda seen: seen
                if seen.get("status") == "available"
                else (_ for _ in ()).throw(
                    SmokeFailure(f"weekly report is {seen.get('status')!r}")
                )
            )(
                request(
                    base,
                    "GET",
                    f"/parents/me/children/{child['id']}/reports/{report_week()}",
                    token=parent,
                )
            ),
        )
    else:
        report.skip("parent journey", "sign-in failed")

    print("\nhuman teacher")
    if not args.include_escalation:
        report.skip("student reaches a human teacher", "pass --include-escalation; consumes weekly allowance")
    elif student and teacher and conversation:
        marker = uuid.uuid4().hex[:8]
        try:
            accepted = escalate(base, student, conversation["id"], marker)
        except AllowanceExhausted:
            # Every run spends one weekly case, so a used-up allowance is the
            # quota working, not the journey breaking.
            accepted = None
            report.skip(
                "student reaches a human teacher", "weekly teacher-support allowance is used"
            )

        escalation = (
            report.check(
                "escalation is accepted and assigned",
                lambda: accepted
                if accepted.get("teacherName")
                else (_ for _ in ()).throw(SmokeFailure("no teacher was assigned")),
            )
            if accepted
            else None
        )
        if escalation:
            report.check(
                "the assigned teacher sees it queued",
                lambda: await_queued(base, teacher, conversation["id"]),
            )
            report.check(
                "the student sees the request was picked up",
                lambda: (
                    lambda seen: seen
                    if seen.get("status") in {"assigned", "in_progress", "resolved"}
                    else (_ for _ in ()).throw(
                        SmokeFailure(f"student still sees status {seen.get('status')!r}")
                    )
                )(
                    request(
                        base,
                        "GET",
                        f"/teacher-help/conversations/{conversation['id']}/request",
                        token=student,
                    )
                ),
            )
    else:
        report.skip("student reaches a human teacher", "a prerequisite failed")

    total = len(report.passed) + len(report.failed)
    print(f"\n{len(report.passed)}/{total} checks passed, {len(report.skipped)} skipped")
    if report.failed:
        print("\nfailures:")
        for name, detail in report.failed:
            print(f"  {name}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
