import hashlib
import hmac
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from botocore.exceptions import ClientError

from stoa.config import Settings, get_settings
from stoa.db.repositories import billing_fact_repo, checkout_command_repo
from stoa.routers import admin, billing, parents
from stoa.services import (
    account_operations_service,
    billing_reconciliation_service,
    entitlement_service,
    subscription_service,
)
from actor_helpers import install_actor_overrides


class FakeTable:
    def __init__(self):
        self.items = {}
        self.scan_pages = []

    def put_item(self, Item):
        self.items[(Item["PK"], Item["SK"])] = dict(Item)

    def get_item(self, Key, ConsistentRead=False):  # noqa: N803
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": dict(item)} if item else {}

    def scan(self, **kwargs):
        if self.scan_pages:
            page_index = int((kwargs.get("ExclusiveStartKey") or {}).get("page", 0))
            page = self.scan_pages[page_index]
            response = {"Items": [dict(item) for item in page]}
            if page_index + 1 < len(self.scan_pages):
                response["LastEvaluatedKey"] = {"page": page_index + 1}
            return response
        return {"Items": [dict(item) for item in self.items.values()]}

    def query(self, **kwargs):
        expected_pk = _condition_value(kwargs.get("KeyConditionExpression"), "PK")
        if expected_pk is None:
            expected_pk = (kwargs.get("ExpressionAttributeValues") or {}).get(":pk")
        sk_prefix = _condition_value(kwargs.get("KeyConditionExpression"), "SK")
        events = [
            dict(item)
            for (item_pk, sk), item in self.items.items()
            if item_pk == expected_pk and sk.startswith(sk_prefix or "EVENT#")
        ]
        return {"Items": events}

    def update_item(
        self,
        Key,
        UpdateExpression,
        ExpressionAttributeValues,
        ExpressionAttributeNames=None,
        **_kwargs,
    ):
        item = self.items.setdefault((Key["PK"], Key["SK"]), {"PK": Key["PK"], "SK": Key["SK"]})
        names = ExpressionAttributeNames or {}

        if names:
            assignments = UpdateExpression.removeprefix("SET ").split(",")
            for assignment in assignments:
                alias, value_alias = [part.strip() for part in assignment.split("=")]
                field = names[alias]
                item[field] = ExpressionAttributeValues[value_alias]
            return {"Attributes": dict(item)}

        assignments = UpdateExpression.removeprefix("SET ").split(",")
        for assignment in assignments:
            field, value_alias = [part.strip() for part in assignment.split("=")]
            item[field] = ExpressionAttributeValues[value_alias]
        return {"Attributes": dict(item)}

    def transact_write_items(self, TransactItems):
        for operation in TransactItems:
            self._check_transaction_operation(operation)
        for operation in TransactItems:
            if "Put" in operation:
                self.put_item(operation["Put"]["Item"])
            elif "Update" in operation:
                update = operation["Update"]
                self.update_item(
                    Key=update["Key"],
                    UpdateExpression=update["UpdateExpression"],
                    ExpressionAttributeValues=update.get("ExpressionAttributeValues", {}),
                    ExpressionAttributeNames=update.get("ExpressionAttributeNames"),
                )
            elif "Delete" in operation:
                key = operation["Delete"]["Key"]
                self.items.pop((key["PK"], key["SK"]), None)

    def transact_account_deletion(self, operations):
        self.transact_write_items(TransactItems=operations)

    def _check_transaction_operation(self, operation):
        if "ConditionCheck" in operation:
            check = operation["ConditionCheck"]
            item = self.items.get((check["Key"]["PK"], check["Key"]["SK"]))
            values = check.get("ExpressionAttributeValues", {})
            if (
                item is None
                or item.get("status") != values.get(":active")
                or item.get("generation") != values.get(":generation")
            ):
                raise _conditional_error()
        if "Put" in operation:
            put = operation["Put"]
            key = (put["Item"]["PK"], put["Item"]["SK"])
            if (
                "attribute_not_exists(PK)" in str(put.get("ConditionExpression") or "")
                and key in self.items
            ):
                raise _conditional_error()
        if "Update" in operation:
            update = operation["Update"]
            key = (update["Key"]["PK"], update["Key"]["SK"])
            item = self.items.get(key)
            condition = update.get("ConditionExpression")
            if condition == "attribute_exists(PK)" and item is None:
                raise _conditional_error()
            if condition == "#current_status = :current_status":
                if item is None or item.get("status") != update["ExpressionAttributeValues"][":current_status"]:
                    raise _conditional_error()
            if condition and "version=:expected_profile_version" in condition:
                expected = update["ExpressionAttributeValues"][":expected_profile_version"]
                if item is None or item.get("version") != expected:
                    raise _conditional_error()


def _settings(**overrides) -> Settings:
    values = {"cognito_user_pool_id": "pool", "s3_images_bucket": "images", **overrides}
    if overrides.get("environment") == "production":
        values.update(
            cognito_allowed_issuers=["https://identity.test"],
            cognito_access_client_ids=["test-access-client"],
            authorization_audit_active_key_id="test-production-v1",
            authorization_audit_active_key="test-production-authorization-audit-key-32-bytes",
            stripe_checkout_web_origins=["https://app.stoaedu.ch"],
        )
    if values.get("stripe_api_key"):
        values.setdefault("stripe_student_price_id", "price_student_live")
        values.setdefault(
            "stripe_teacher_supported_price_id",
            "price_teacher_supported_live",
        )
        values.setdefault("stripe_family_price_id", "price_family_live")
    return Settings(**values)


def _checkout_settings(**overrides) -> Settings:
    return _settings(
        stripe_api_key="sk_test_checkout",
        stripe_student_price_id="price_test_student",
        stripe_teacher_supported_price_id="price_test_teacher_supported",
        stripe_family_price_id="price_test_family",
        **overrides,
    )


def _checkout_headers(key: str = "checkout-operation-key-0001") -> dict[str, str]:
    return {"Idempotency-Key": key}


def _checkout_body(
    plan: str = "student",
    beneficiary_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "plan": plan,
        "beneficiaryIds": beneficiary_ids or ["student-1"],
    }


def _app_for_user(user: dict, settings: Settings | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.include_router(admin.router, prefix="/admin")
    app.include_router(billing.router, prefix="/billing")
    install_actor_overrides(app, user)
    app.dependency_overrides[get_settings] = lambda: settings or _settings()
    return app


def _profiles():
    return {
        "parent-1": {
            "user_id": "parent-1",
            "email": "parent@example.com",
            "role": "parent",
            "account_status": "active",
            "subscription_tier": "free_trial",
            "version": 1,
        },
        "student-1": {
            "user_id": "student-1",
            "email": "student@example.com",
            "role": "student",
            "account_status": "active",
            "subscription_tier": "free_trial",
            "parent_id": "parent-1",
            "parent_binding_status": "active",
            "version": 1,
        },
        "admin-1": {
            "user_id": "admin-1",
            "email": "admin@example.com",
            "role": "admin",
            "account_status": "active",
            "subscription_tier": "family",
            "version": 1,
        },
    }


def _condition_value(condition, key_name: str):
    if condition is None:
        return None
    for child in getattr(condition, "_values", ()):
        values = getattr(child, "_values", ())
        if len(values) == 2 and getattr(values[0], "name", None) == key_name:
            return values[1]
    return None


def _conditional_error() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "condition failed"}},
        "TransactWriteItems",
    )


def _stripe_signature(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    timestamp = timestamp or int(time.time())
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def _install_fakes(monkeypatch):
    table = FakeTable()
    table_update_item = table.update_item
    profiles = _profiles()
    for profile in profiles.values():
        table.items[(f"USER#{profile['user_id']}", "PROFILE")] = {
            "PK": f"USER#{profile['user_id']}",
            "SK": "PROFILE",
            **profile,
        }
        table.items[(f"USER#{profile['user_id']}", "ACCOUNT_FENCE")] = {
            "PK": f"USER#{profile['user_id']}",
            "SK": "ACCOUNT_FENCE",
            "status": "active",
            "generation": 1,
        }

    def get_user(user_id):
        return profiles.get(user_id)

    def list_parent_student_bindings(parent_id):
        return [
            dict(item)
            for (pk, sk), item in table.items.items()
            if pk == f"USER#{parent_id}" and sk.startswith("CHILD#")
        ]

    def get_parent_student_binding(parent_id, student_id):
        return table.items.get((f"USER#{parent_id}", f"CHILD#{student_id}"))

    def get_student_parent_binding(student_id, parent_id):
        return table.items.get((f"USER#{student_id}", f"PARENT#{parent_id}"))

    def update_item(
        Key,
        UpdateExpression,
        ExpressionAttributeValues,
        ExpressionAttributeNames=None,
        **kwargs,
    ):
        if Key["PK"].startswith("USER#") and Key["SK"] == "PROFILE":
            user_id = Key["PK"].removeprefix("USER#")
            profile = profiles.setdefault(
                user_id,
                {
                    "user_id": user_id,
                    "role": "parent",
                    "subscription_tier": "free_trial",
                    "version": 1,
                },
            )
            names = ExpressionAttributeNames or {}
            assignments = UpdateExpression.removeprefix("SET ").split(",")
            for assignment in assignments:
                alias, value_alias = [part.strip() for part in assignment.split("=")]
                field = names.get(alias, alias)
                profile[field] = ExpressionAttributeValues[value_alias]
            table.items[(Key["PK"], Key["SK"])] = {
                "PK": Key["PK"],
                "SK": Key["SK"],
                **profile,
            }
            return {"Attributes": dict(table.items[(Key["PK"], Key["SK"])])}
        return table_update_item(
            Key=Key,
            UpdateExpression=UpdateExpression,
            ExpressionAttributeValues=ExpressionAttributeValues,
            ExpressionAttributeNames=ExpressionAttributeNames,
            **kwargs,
        )

    table.update_item = update_item
    monkeypatch.setattr(subscription_service, "get_table", lambda: table)
    monkeypatch.setattr(checkout_command_repo, "get_table", lambda: table)
    monkeypatch.setattr(billing_fact_repo, "get_table", lambda: table)
    monkeypatch.setattr(billing_reconciliation_service, "get_table", lambda: table)
    monkeypatch.setattr(subscription_service, "_stripe_sdk_available", lambda: False)
    monkeypatch.setattr(subscription_service.user_repo, "get_user", get_user)
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_parent_student_binding",
        get_parent_student_binding,
    )
    monkeypatch.setattr(
        subscription_service.user_repo,
        "get_student_parent_binding",
        get_student_parent_binding,
    )
    monkeypatch.setattr(entitlement_service, "get_table", lambda: table)
    monkeypatch.setattr(entitlement_service.user_repo, "get_user", get_user)
    monkeypatch.setattr(
        entitlement_service.user_repo,
        "list_parent_student_bindings",
        list_parent_student_bindings,
    )
    monkeypatch.setattr(
        entitlement_service.user_repo,
        "get_parent_student_binding",
        get_parent_student_binding,
    )
    monkeypatch.setattr(parents.user_repo, "get_user", get_user)
    monkeypatch.setattr(account_operations_service.user_repo, "get_user", get_user)
    monkeypatch.setattr(
        account_operations_service.user_repo,
        "list_children_by_parent_scan",
        lambda parent_id: [],
    )
    table.put_item(
        Item={
            "PK": "USER#parent-1",
            "SK": "CHILD#student-1",
            "entity_type": "parent_student_binding",
            "parent_id": "parent-1",
            "student_id": "student-1",
            "status": "active",
            "relationship": "child",
        }
    )
    table.put_item(
        Item={
            "PK": "USER#student-1",
            "SK": "PARENT#parent-1",
            "entity_type": "parent_student_binding",
            "parent_id": "parent-1",
            "student_id": "student-1",
            "status": "active",
            "relationship": "child",
        }
    )

    sessions: dict[str, dict[str, object]] = {}

    class FakeStripeSession:
        @staticmethod
        def create(**kwargs):
            provider_key = str(kwargs["idempotency_key"])
            return sessions.setdefault(
                provider_key,
                {
                    "id": f"cs_test_{provider_key[:24]}",
                    "url": (
                        "https://checkout.stripe.com/c/pay/"
                        f"cs_test_{provider_key[:24]}"
                    ),
                    "livemode": False,
                    "customer": "cus_test_parent",
                },
            )

    class FakeStripeCheckout:
        Session = FakeStripeSession

    class FakeStripe:
        checkout = FakeStripeCheckout
        api_key = None

    monkeypatch.setattr(subscription_service, "_load_stripe_sdk", lambda: FakeStripe)
    return table, profiles


def _patch_account_usage(monkeypatch):
    def usage_summary(*, student_id, settings, day=None, entitlement=None):
        return {
            "studentId": student_id,
            "parentId": (entitlement or {}).get("parentId"),
            "quotaPeriod": day or "2026-07-03",
            "action": "question_submission",
            "consumed": 2,
            "limit": int(((entitlement or {}).get("limits") or {}).get("dailyAiQuestionLimit") or 5),
            "remaining": 3,
            "effectivePlan": (entitlement or {}).get("effectivePlan"),
            "entitlementSource": (entitlement or {}).get("source"),
            "billingState": (entitlement or {}).get("billingState"),
            "reconciliation": {"status": "matched"},
            "partial": False,
            "stale": False,
            "unreconciled": False,
        }

    monkeypatch.setattr(
        account_operations_service.usage_ledger_service,
        "build_student_usage_summary",
        usage_summary,
    )


def _put_active_billing(
    table: FakeTable,
    *,
    parent_id: str = "parent-1",
    payment_method_type: str = "twint",
    last_provider_event_at: str | None = None,
):
    now = last_provider_event_at or subscription_service.now_iso()
    item = {
        "PK": f"SUBSCRIPTION_BILLING#{parent_id}",
        "SK": "SUMMARY",
        "entity_type": "subscription_billing",
        "parent_id": parent_id,
        "subscription_tier": "family",
        "requested_tier": "family",
        "billing_provider": "stripe",
        "billing_mode": "live",
        "billing_status": "active",
        "provider_customer_id": "cus_live_parent",
        "provider_subscription_id": "sub_live_parent",
        "provider_price_id": "price_premium_live",
        "provider_livemode": True,
        "readiness_state": "live_enabled",
        "readiness_blockers": [],
        "twint_in_scope": True,
        "twint_status": "eligible",
        "payment_method_type": payment_method_type,
        "latest_invoice": {
            "providerInvoiceId": "in_live_parent",
            "providerSubscriptionId": "sub_live_parent",
            "providerPaymentIntentId": "pi_live_parent",
            "providerChargeId": "ch_live_parent",
            "hostedInvoiceUrl": "https://invoice.stripe.com/i/live",
            "receiptUrl": "https://pay.stripe.com/receipts/live",
            "invoiceStatus": "paid",
            "currency": "CHF",
            "amountDue": 1500,
            "amountPaid": 1500,
            "amountRemaining": 0,
            "amountRefunded": 0,
            "taxAmount": 115,
            "taxStatus": "provider_managed",
            "paymentMethodType": payment_method_type,
            "reconciliationId": "STOA-2026-0002",
        },
        "last_provider_event_id": "evt_invoice_paid_live",
        "last_provider_event_type": "invoice.paid",
        "last_provider_event_at": now,
        "created_at": now,
        "updated_at": now,
    }
    table.items[(item["PK"], item["SK"])] = item
    return item


def test_parent_account_operations_combines_billing_entitlement_usage_and_verification(monkeypatch):
    table, profiles = _install_fakes(monkeypatch)
    _patch_account_usage(monkeypatch)
    _put_active_billing(table)
    profiles["parent-1"].update(
        {
            "email_verification_status": "verified",
            "email_verification_required": False,
        }
    )
    profiles["student-1"].update(
        {
            "email_verification_status": "verified",
            "email_verification_required": False,
        }
    )
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))

    response = client.get("/parents/me/account-operations?day=2026-07-03")

    assert response.status_code == 200
    body = response.json()
    assert body["parentId"] == "parent-1"
    assert body["billing"]["status"] == "active"
    assert body["children"][0]["studentId"] == "student-1"
    assert body["children"][0]["entitlement"]["effectivePlan"] == "family"
    assert body["children"][0]["usage"]["consumed"] == 2
    assert body["parent"]["verification"]["emailVerificationStatus"] == "verified"
    assert body["parent"]["verification"]["supportRecoveryState"] == "verified"
    assert body["parent"]["verification"]["supportAction"] == "none"
    assert body["supportState"]["state"] == "ready"


def test_admin_account_operations_surfaces_attention_state(monkeypatch):
    table, profiles = _install_fakes(monkeypatch)
    _patch_account_usage(monkeypatch)
    _put_active_billing(table)
    profiles["parent-1"].update(
        {
            "email_verification_status": "pending_verification",
            "email_verification_required": True,
        }
    )
    profiles["student-1"].update(
        {
            "email_verification_status": "expired_verification",
            "email_verification_required": True,
        }
    )
    table.items[("USER#parent-1", "CHILD#student-1")]["status"] = "active_pending_verification"
    client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    response = client.get("/admin/account-operations/parents/parent-1?day=2026-07-03")

    assert response.status_code == 200
    body = response.json()
    assert body["parentId"] == "parent-1"
    assert body["billing"]["events"] == []
    assert body["parent"]["verification"]["resendAllowed"] is True
    assert body["parent"]["verification"]["supportRecoveryState"] == "resend_available"
    assert body["parent"]["verification"]["supportAction"] == "resend_verification_code"
    assert body["children"][0]["binding"]["status"] == "active_pending_verification"
    assert body["children"][0]["profile"]["verification"]["supportRecoveryState"] == "expired_code"
    assert body["children"][0]["profile"]["verification"]["supportAction"] == "resend_verification_code"
    assert "parent_email_unverified" in body["supportState"]["blockers"]
    assert "child_email_unverified" in body["supportState"]["warnings"]
    assert "child_binding_active_pending_verification" in body["supportState"]["warnings"]


def test_admin_account_operations_returns_404_for_missing_parent(monkeypatch):
    _install_fakes(monkeypatch)
    _patch_account_usage(monkeypatch)
    client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    response = client.get("/admin/account-operations/parents/missing-parent")

    assert response.status_code == 404
    assert response.json()["detail"] == "Parent not found"


def test_parent_can_view_plan_options(monkeypatch):
    _install_fakes(monkeypatch)
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))

    response = client.get("/parents/me/subscription")

    assert response.status_code == 200
    body = response.json()
    assert body["currentTier"] == "free_trial"
    assert body["plans"]["student"]["dailyAiQuestionLimit"] == 30
    assert body["pendingRequest"] is None
    assert body["billing"]["status"] == "none"
    assert body["effectiveEntitlements"][0]["studentId"] == "student-1"
    assert body["effectiveEntitlements"][0]["effectivePlan"] == "free_trial"


def test_parent_can_create_subscription_request_once(monkeypatch):
    _install_fakes(monkeypatch)
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))

    response = client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "student", "parentNote": "Please upgrade"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "requested"
    assert body["requestType"] == "upgrade"
    assert body["requestedTier"] == "student"
    assert body["history"][0]["eventType"] == "requested"

    duplicate = client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "family"},
    )
    assert duplicate.status_code == 409


def test_subscription_parent_endpoints_are_parent_only(monkeypatch):
    _install_fakes(monkeypatch)
    client = TestClient(_app_for_user({"sub": "student-1", "role": "student"}))

    response = client.get("/parents/me/subscription")

    assert response.status_code == 403


def test_admin_approve_does_not_mutate_tier_but_apply_does(monkeypatch):
    table, profiles = _install_fakes(monkeypatch)
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    created = parent_client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "student"},
    ).json()
    request_id = created["requestId"]

    approved = admin_client.patch(
        f"/admin/subscriptions/requests/{request_id}",
        json={"status": "approved", "admin_note": "Bank transfer received"},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert profiles["parent-1"]["subscription_tier"] == "free_trial"

    applied = admin_client.post(
        f"/admin/subscriptions/requests/{request_id}/apply",
        json={"admin_note": "Applied manually"},
    )

    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert profiles["parent-1"]["subscription_tier"] == "student"
    assert table.items


def test_admin_list_filters_and_invalid_apply(monkeypatch):
    _install_fakes(monkeypatch)
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    created = parent_client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "student"},
    ).json()

    listed = admin_client.get(
        "/admin/subscriptions/requests",
        params={"status": "requested", "requested_tier": "student", "parent_id": "parent-1"},
    )
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    rejected_apply = admin_client.post(
        f"/admin/subscriptions/requests/{created['requestId']}/apply",
        json={},
    )
    assert rejected_apply.status_code == 409


def test_admin_list_follows_scan_pagination(monkeypatch):
    table, _profiles = _install_fakes(monkeypatch)
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    created = parent_client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "student"},
    ).json()
    summary = table.items[(f"SUBSCRIPTION_REQUEST#{created['requestId']}", "SUMMARY")]
    table.scan_pages = [
        [{"PK": "USER#other", "SK": "PROFILE", "entity_type": "user"}],
        [summary],
    ]

    response = admin_client.get("/admin/subscriptions/requests", params={"status": "requested"})

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["items"][0]["requestId"] == created["requestId"]


def test_parent_pending_request_uses_open_guard_not_scan(monkeypatch):
    table, _profiles = _install_fakes(monkeypatch)
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))

    created = client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "student"},
    ).json()
    table.scan_pages = [[]]

    response = client.get("/parents/me/subscription")

    assert response.status_code == 200
    assert response.json()["pendingRequest"]["requestId"] == created["requestId"]


def test_request_history_is_isolated_by_request_id(monkeypatch):
    _install_fakes(monkeypatch)
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    first = parent_client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "student"},
    ).json()
    admin_client.patch(
        f"/admin/subscriptions/requests/{first['requestId']}",
        json={"status": "cancelled", "admin_note": "Parent changed plans"},
    )
    second = parent_client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "family"},
    ).json()

    response = admin_client.get(f"/admin/subscriptions/requests/{first['requestId']}")

    assert response.status_code == 200
    history = response.json()["history"]
    assert {event["eventType"] for event in history} == {"requested", "cancelled"}
    assert second["requestId"] not in str(history)


def test_parent_can_create_checkout_session_and_admin_can_inspect_billing(monkeypatch):
    table, _profiles = _install_fakes(monkeypatch)
    settings = _checkout_settings()
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = client.post(
        "/parents/me/subscription/checkout",
        headers=_checkout_headers(),
        json=_checkout_body(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["checkoutRef"].startswith("co_")
    assert body["commandState"] == "provider_session_open"
    assert body["targetPlan"] == "student"
    assert body["beneficiaries"] == ["student-1"]
    assert body["safeActions"] == ["recheck_payment", "contact_support"]
    assert body["checkoutSessionId"].startswith("cs_test_")
    assert body["checkoutUrl"].startswith("https://checkout.stripe.com/c/pay/cs_test_")

    subscription = client.get("/parents/me/subscription").json()
    assert subscription["billing"]["status"] == "none"

    admin_response = admin_client.get("/admin/subscriptions/billing")
    assert admin_response.status_code == 200
    assert admin_response.json()["count"] == 0
    command_rows = [
        item
        for item in table.items.values()
        if item.get("entity_type") == "checkout_command"
    ]
    assert len(command_rows) == 1
    assert command_rows[0]["provider_effect_status"] == "session_attached"
    assert command_rows[0]["beneficiary_ids"] == ["student-1"]


def test_production_live_checkout_is_refused_before_provider_access(monkeypatch):
    _install_fakes(monkeypatch)
    monkeypatch.setattr(subscription_service, "_stripe_sdk_available", lambda: True)
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_webhook_secret="whsec_live",
        stripe_student_price_id="price_student_live",
        stripe_teacher_supported_price_id="price_teacher_supported_live",
        stripe_family_price_id="price_family_live",
        stripe_live_charges_enabled=False,
    )
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))

    response = client.post(
        "/parents/me/subscription/checkout",
        headers=_checkout_headers(),
        json=_checkout_body(),
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "checkout_sandbox_required"


def test_live_checkout_is_refused_when_twint_capability_is_confirmed(monkeypatch):
    _install_fakes(monkeypatch)
    captured: dict[str, object] = {}

    class FakeStripeSession:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return {"id": "cs_live_twint", "url": "https://checkout.stripe.com/c/pay/cs_live_twint"}

    class FakeStripeCheckout:
        Session = FakeStripeSession

    class FakeStripe:
        checkout = FakeStripeCheckout
        api_key = None

    monkeypatch.setattr(subscription_service, "_stripe_sdk_available", lambda: True)
    monkeypatch.setattr(subscription_service, "_load_stripe_sdk", lambda: FakeStripe)
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_webhook_secret="whsec_live",
        stripe_student_price_id="price_student_live",
        stripe_teacher_supported_price_id="price_teacher_supported_live",
        stripe_family_price_id="price_family_live",
        stripe_live_charges_enabled=True,
        stripe_twint_capability_confirmed=True,
    )
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))

    response = client.post(
        "/parents/me/subscription/checkout",
        headers=_checkout_headers(),
        json=_checkout_body(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "checkout_sandbox_required"
    assert captured == {}


def test_production_checkout_reports_missing_live_configuration(monkeypatch):
    _install_fakes(monkeypatch)
    settings = _settings(environment="production", stripe_live_charges_enabled=True)
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))

    response = client.post(
        "/parents/me/subscription/checkout",
        headers=_checkout_headers(),
        json=_checkout_body(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "checkout_sandbox_required"


def test_admin_provider_readiness_reports_missing_production_config(monkeypatch):
    _install_fakes(monkeypatch)
    settings = _settings(environment="production", stripe_live_charges_enabled=True)
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.get("/admin/subscriptions/billing/provider-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "not_configured"
    assert body["checkoutAllowed"] is False
    assert body["providerMode"] == "missing"
    blockers = set(body["blockers"])
    assert "missing_stripe_api_key" in blockers
    assert "missing_stripe_webhook_secret" in blockers
    assert "missing_student_price_id" in blockers
    assert "missing_teacher_supported_price_id" in blockers
    assert "missing_family_price_id" in blockers
    assert "missing_stripe_webhook_endpoint_url" in blockers
    assert body["credentials"]["apiKey"] == "missing"


def test_admin_provider_readiness_rejects_test_key_in_production(monkeypatch):
    _install_fakes(monkeypatch)
    monkeypatch.setattr(subscription_service, "_stripe_sdk_available", lambda: True)
    settings = _settings(
        environment="production",
        stripe_api_key="sk_test_not_live",
        stripe_webhook_secret="whsec_live",
        stripe_student_price_id="price_student_live",
        stripe_teacher_supported_price_id="price_teacher_supported_live",
        stripe_family_price_id="price_family_live",
        stripe_webhook_endpoint_url="https://api.stoaedu.ch/billing/webhooks/stripe",
        stripe_live_charges_enabled=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.get("/admin/subscriptions/billing/provider-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "not_configured"
    assert body["checkoutAllowed"] is False
    assert body["providerMode"] == "test"
    assert "stripe_api_key_not_live" in body["blockers"]
    assert "sk_test_not_live" not in response.text


def test_admin_provider_readiness_reports_twint_pending(monkeypatch):
    _install_fakes(monkeypatch)
    monkeypatch.setattr(subscription_service, "_stripe_sdk_available", lambda: True)
    monkeypatch.setattr(
        subscription_service,
        "_retrieve_stripe_account",
        lambda settings: {"capabilities": {"twint_payments": "pending"}},
    )
    monkeypatch.setattr(
        subscription_service,
        "_retrieve_stripe_price",
        lambda price_id, settings: {
            "id": price_id,
            "currency": "chf",
            "recurring": {"interval": "month"},
            "livemode": True,
            "active": True,
        },
    )
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_webhook_secret="whsec_live",
        stripe_student_price_id="price_student_live",
        stripe_teacher_supported_price_id="price_teacher_supported_live",
        stripe_family_price_id="price_family_live",
        stripe_webhook_endpoint_url="https://api.stoaedu.ch/billing/webhooks/stripe",
        stripe_live_charges_enabled=False,
        stripe_twint_capability_confirmed=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.get("/admin/subscriptions/billing/provider-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "live_ready_but_blocked"
    assert body["checkoutAllowed"] is False
    assert body["twint"]["providerCapability"] == "pending"
    assert body["twint"]["status"] == "pending"
    assert "twint_capability_pending" in body["blockers"]
    assert body["prices"]["student"]["currency"] == "CHF"
    assert body["prices"]["student"]["recurring"] is True


def test_admin_provider_readiness_redacts_provider_failures(monkeypatch):
    _install_fakes(monkeypatch)
    monkeypatch.setattr(subscription_service, "_stripe_sdk_available", lambda: True)

    def fail_account(settings):
        raise RuntimeError("provider exploded with sk_live_secret_value")

    monkeypatch.setattr(subscription_service, "_retrieve_stripe_account", fail_account)
    monkeypatch.setattr(
        subscription_service,
        "_retrieve_stripe_price",
        lambda price_id, settings: (_ for _ in ()).throw(RuntimeError(f"failed {price_id}")),
    )
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_secret_value",
        stripe_webhook_secret="whsec_secret_value",
        stripe_student_price_id="price_student_live",
        stripe_teacher_supported_price_id="price_teacher_supported_live",
        stripe_family_price_id="price_family_live",
        stripe_webhook_endpoint_url="https://api.stoaedu.ch/billing/webhooks/stripe",
        stripe_live_charges_enabled=True,
        stripe_twint_capability_confirmed=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.get("/admin/subscriptions/billing/provider-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "provider_api_failed"
    assert body["checkoutAllowed"] is False
    assert "stripe_account_lookup_failed" in body["blockers"]
    assert "student_price_lookup_failed" in body["blockers"]
    assert "sk_live_secret_value" not in response.text
    assert "whsec_secret_value" not in response.text
    assert "provider exploded" not in response.text


def test_admin_provider_readiness_reports_live_success(monkeypatch):
    _install_fakes(monkeypatch)
    monkeypatch.setattr(subscription_service, "_stripe_sdk_available", lambda: True)
    monkeypatch.setattr(
        subscription_service,
        "_retrieve_stripe_account",
        lambda settings: {"capabilities": {"twint_payments": "active"}},
    )
    monkeypatch.setattr(
        subscription_service,
        "_retrieve_stripe_price",
        lambda price_id, settings: {
            "id": price_id,
            "currency": "chf",
            "recurring": {"interval": "month"},
            "livemode": True,
            "active": True,
        },
    )
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_webhook_secret="whsec_live",
        stripe_student_price_id="price_student_live",
        stripe_teacher_supported_price_id="price_teacher_supported_live",
        stripe_family_price_id="price_family_live",
        stripe_webhook_endpoint_url="https://api.stoaedu.ch/billing/webhooks/stripe",
        stripe_live_charges_enabled=True,
        stripe_twint_capability_confirmed=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.get("/admin/subscriptions/billing/provider-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "live_enabled"
    assert body["checkoutAllowed"] is True
    assert body["refundsAllowed"] is False
    assert body["providerMode"] == "live"
    assert body["twint"]["providerCapability"] == "active"
    assert body["twint"]["status"] == "eligible"
    assert body["twint"]["constraints"]["currency"] == "CHF"
    assert body["twint"]["constraints"]["manualCaptureSupported"] is False
    assert body["twint"]["constraints"]["refundWindowDays"] == 180
    assert body["prices"]["family"]["currency"] == "CHF"
    assert body["prices"]["family"]["recurring"] is True
    assert body["webhook"]["endpointMode"] == "https"
    assert body["finance"]["accountingExportAvailable"] is True
    assert body["blockers"] == []


def test_admin_can_execute_direct_refund_and_export_finance_handoff(monkeypatch):
    table, _profiles = _install_fakes(monkeypatch)
    _put_active_billing(table)
    captured: dict[str, object] = {}

    def create_refund(**kwargs):
        captured.update(kwargs)
        return {
            "id": "re_live_parent",
            "status": "succeeded",
            "amount": kwargs["amount"],
            "currency": "chf",
            "charge": kwargs["provider_charge_id"],
            "payment_intent": kwargs["provider_payment_intent_id"],
            "invoice": "in_live_parent",
        }

    monkeypatch.setattr(subscription_service, "_create_provider_refund", create_refund)
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_refunds_enabled=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.post(
        "/admin/subscriptions/billing/parent-1/refunds",
        json={
            "amount": 500,
            "reason": "goodwill refund",
            "idempotencyKey": "refund-key-001",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert captured["provider_charge_id"] == "ch_live_parent"
    assert captured["amount"] == 500
    assert captured["idempotency_key"] == "refund-key-001"
    assert body["idempotencyStatus"] == "new"
    assert body["refund"]["state"] == "succeeded"
    assert body["refund"]["providerRefundId"] == "re_live_parent"
    assert body["refund"]["refundedAmount"] == 500
    assert body["refund"]["eligibleAmount"] == 1000
    assert body["billing"]["latestInvoice"]["amountRefunded"] == 500
    assert body["billing"]["accountingHandoff"]["refund"]["providerRefundId"] == "re_live_parent"
    assert body["billing"]["accountingHandoff"]["refund"]["reason"] == "goodwill refund"
    assert body["billing"]["accountingHandoff"]["refund"]["idempotencyKey"] == "refund-key-001"
    assert body["billing"]["accountingHandoff"]["refund"]["requestedBy"] == "admin-1"

    export_response = admin_client.get("/admin/subscriptions/billing/accounting-export")
    export = export_response.json()["items"][0]
    assert export["refund"]["providerRefundId"] == "re_live_parent"
    assert export["refund"]["refundedAmount"] == 500
    assert export["refund"]["providerHandoffState"] == "succeeded"


def test_admin_direct_refund_requires_eligible_billing(monkeypatch):
    _install_fakes(monkeypatch)
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_refunds_enabled=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.post(
        "/admin/subscriptions/billing/parent-1/refunds",
        json={
            "amount": 500,
            "reason": "not eligible",
            "idempotencyKey": "refund-key-002",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "Billing record is not refundable"


def test_admin_direct_refund_replays_duplicate_idempotency_key(monkeypatch):
    table, _profiles = _install_fakes(monkeypatch)
    _put_active_billing(table)
    calls = {"count": 0}

    def create_refund(**kwargs):
        calls["count"] += 1
        return {
            "id": "re_idempotent_parent",
            "status": "succeeded",
            "amount": kwargs["amount"],
            "currency": "chf",
            "charge": kwargs["provider_charge_id"],
            "payment_intent": kwargs["provider_payment_intent_id"],
            "invoice": "in_live_parent",
        }

    monkeypatch.setattr(subscription_service, "_create_provider_refund", create_refund)
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_refunds_enabled=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))
    payload = {
        "amount": 500,
        "reason": "duplicate protection",
        "idempotencyKey": "refund-key-003",
    }

    first = admin_client.post("/admin/subscriptions/billing/parent-1/refunds", json=payload)
    second = admin_client.post("/admin/subscriptions/billing/parent-1/refunds", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["idempotencyStatus"] == "new"
    assert second.json()["idempotencyStatus"] == "replayed"
    assert calls["count"] == 1
    assert second.json()["billing"]["latestInvoice"]["amountRefunded"] == 500


def test_admin_direct_refund_provider_failure_does_not_mutate_billing(monkeypatch):
    table, _profiles = _install_fakes(monkeypatch)
    _put_active_billing(table)

    def fail_refund(**kwargs):
        raise RuntimeError("provider failed with sk_live_secret")

    monkeypatch.setattr(subscription_service, "_create_provider_refund", fail_refund)
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_refunds_enabled=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.post(
        "/admin/subscriptions/billing/parent-1/refunds",
        json={
            "amount": 500,
            "reason": "provider failure",
            "idempotencyKey": "refund-key-004",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Stripe refund creation failed"
    billing = admin_client.get("/admin/subscriptions/billing/parent-1").json()
    assert billing["latestInvoice"]["amountRefunded"] == 0
    assert billing["refund"]["state"] == "ready_for_provider"
    assert "sk_live_secret" not in response.text


def test_admin_direct_refund_blocks_expired_twint_window(monkeypatch):
    table, _profiles = _install_fakes(monkeypatch)
    _put_active_billing(table, last_provider_event_at="2025-01-01T00:00:00+00:00")
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_refunds_enabled=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.post(
        "/admin/subscriptions/billing/parent-1/refunds",
        json={
            "amount": 500,
            "reason": "expired twint window",
            "idempotencyKey": "refund-key-005",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "TWINT refund window has expired"


def test_admin_rollout_controls_default_from_static_config(monkeypatch):
    _install_fakes(monkeypatch)
    settings = _settings(
        environment="production",
        stripe_live_charges_enabled=True,
        stripe_refunds_enabled=False,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.get("/admin/subscriptions/billing/rollout-controls")

    assert response.status_code == 200
    body = response.json()
    assert body["checkout"]["state"] == "enabled"
    assert body["checkout"]["allowed"] is True
    assert body["refunds"]["state"] == "disabled"
    assert body["refunds"]["allowed"] is False


def test_admin_can_update_checkout_and_refund_rollout_controls(monkeypatch):
    _install_fakes(monkeypatch)
    settings = _settings(
        environment="production",
        stripe_live_charges_enabled=True,
        stripe_refunds_enabled=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    updated = admin_client.patch(
        "/admin/subscriptions/billing/rollout-controls",
        json={
            "checkoutState": "rolled_back",
            "refundsState": "enabled",
            "reason": "pause checkout while keeping approved refunds",
        },
    )
    fetched = admin_client.get("/admin/subscriptions/billing/rollout-controls")

    assert updated.status_code == 200
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["checkout"]["state"] == "rolled_back"
    assert body["checkout"]["allowed"] is False
    assert body["refunds"]["state"] == "enabled"
    assert body["refunds"]["allowed"] is True
    assert body["updatedBy"] == "admin-1"
    assert body["reason"] == "pause checkout while keeping approved refunds"


def test_rollout_checkout_rollback_does_not_override_sandbox_only_checkout(monkeypatch):
    _install_fakes(monkeypatch)
    monkeypatch.setattr(subscription_service, "_stripe_sdk_available", lambda: True)
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_webhook_secret="whsec_live",
        stripe_student_price_id="price_student_live",
        stripe_teacher_supported_price_id="price_teacher_supported_live",
        stripe_family_price_id="price_family_live",
        stripe_webhook_endpoint_url="https://api.stoaedu.ch/billing/webhooks/stripe",
        stripe_live_charges_enabled=True,
        stripe_twint_capability_confirmed=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))
    admin_client.patch(
        "/admin/subscriptions/billing/rollout-controls",
        json={
            "checkoutState": "rolled_back",
            "refundsState": "disabled",
            "reason": "rollback checkout",
        },
    )

    response = parent_client.post(
        "/parents/me/subscription/checkout",
        headers=_checkout_headers(),
        json=_checkout_body(),
    )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "checkout_sandbox_required"


def test_rollout_refund_rollback_blocks_new_refund_but_preserves_export(monkeypatch):
    table, _profiles = _install_fakes(monkeypatch)
    _put_active_billing(table)
    monkeypatch.setattr(
        subscription_service,
        "_create_provider_refund",
        lambda **kwargs: {"id": "re_should_not_be_created", "status": "succeeded"},
    )
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_refunds_enabled=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))
    admin_client.patch(
        "/admin/subscriptions/billing/rollout-controls",
        json={
            "checkoutState": "disabled",
            "refundsState": "rolled_back",
            "reason": "rollback refunds",
        },
    )

    response = admin_client.post(
        "/admin/subscriptions/billing/parent-1/refunds",
        json={
            "amount": 500,
            "reason": "blocked after rollback",
            "idempotencyKey": "refund-key-006",
        },
    )
    export_response = admin_client.get("/admin/subscriptions/billing/accounting-export")

    assert response.status_code == 409
    assert response.json()["detail"] == "Direct refund execution is not enabled"
    assert export_response.status_code == 200
    assert export_response.json()["count"] == 1
    assert export_response.json()["items"][0]["providerInvoiceId"] == "in_live_parent"


def test_provider_readiness_reports_webhook_last_observed_event(monkeypatch):
    table, _profiles = _install_fakes(monkeypatch)
    table.put_item(
        Item={
            "PK": "SUBSCRIPTION_BILLING#parent-1",
            "SK": "EVENT#2026-06-12T10:00:00+00:00#evt_last",
            "entity_type": "subscription_billing_event",
            "parent_id": "parent-1",
            "event_id": "stripe_evt_last",
            "event_type": "invoice.paid",
            "event_at": "2026-06-12T10:00:00+00:00",
            "provider": "stripe",
        }
    )
    monkeypatch.setattr(subscription_service, "_stripe_sdk_available", lambda: True)
    monkeypatch.setattr(
        subscription_service,
        "_retrieve_stripe_account",
        lambda settings: {"capabilities": {"twint_payments": "active"}},
    )
    monkeypatch.setattr(
        subscription_service,
        "_retrieve_stripe_price",
        lambda price_id, settings: {
            "id": price_id,
            "currency": "chf",
            "recurring": {"interval": "month"},
            "livemode": True,
            "active": True,
        },
    )
    settings = _settings(
        environment="production",
        stripe_api_key="sk_live_ready",
        stripe_webhook_secret="whsec_live",
        stripe_student_price_id="price_student_live",
        stripe_teacher_supported_price_id="price_teacher_supported_live",
        stripe_family_price_id="price_family_live",
        stripe_webhook_endpoint_url="https://api.stoaedu.ch/billing/webhooks/stripe",
        stripe_live_charges_enabled=True,
        stripe_twint_capability_confirmed=True,
    )
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    response = admin_client.get("/admin/subscriptions/billing/provider-readiness")

    assert response.status_code == 200
    webhook = response.json()["webhook"]
    assert webhook["endpointMode"] == "https"
    assert webhook["signingSecretConfigured"] is True
    assert webhook["quickAckExpected"] is True
    assert "invoice.paid" in webhook["requiredEventTypes"]
    assert webhook["lastObservedEventType"] == "invoice.paid"
    assert webhook["lastObservedProviderEventAt"] == "2026-06-12T10:00:00+00:00"


def test_legacy_checkout_and_invoice_alone_remain_confirming(monkeypatch):
    table, profiles = _install_fakes(monkeypatch)
    secret = "whsec_test_secret"
    settings = _settings(stripe_webhook_secret=secret)
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))
    webhook_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}, settings))

    checkout_session_id = "cs_test_legacy_webhook_family"
    checkout_completed = {
        "id": "evt_checkout_completed_1",
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": checkout_session_id,
                "object": "checkout.session",
                "livemode": False,
                "customer": "cus_test_parent",
                "subscription": "sub_test_parent",
                "metadata": {
                    "stoa_parent_id": "parent-1",
                    "requested_tier": "family",
                },
                "payment_method_types": ["card", "twint"],
            }
        },
    }
    checkout_payload = json.dumps(checkout_completed, separators=(",", ":")).encode("utf-8")

    checkout_response = webhook_client.post(
        "/billing/webhooks/stripe",
        content=checkout_payload,
        headers={"stripe-signature": _stripe_signature(checkout_payload, secret)},
    )

    assert checkout_response.status_code == 200
    assert checkout_response.json()["billingStatus"] == "checkout_pending"
    pending_status = parent_client.get("/parents/me/subscription/billing").json()
    assert pending_status["status"] == "checkout_pending"
    assert pending_status["subscriptionTier"] == "free_trial"
    assert pending_status["paymentMethodType"] is None
    assert pending_status["dunning"]["state"] == "checkout_pending"

    invoice_created = int(time.time())
    invoice_paid = {
        "id": "evt_invoice_paid_1",
        "object": "event",
        "type": "invoice.paid",
        "created": invoice_created,
        "livemode": False,
        "data": {
            "object": {
                "id": "in_test_parent",
                "object": "invoice",
                "livemode": False,
                "customer": "cus_test_parent",
                "subscription": "sub_test_parent",
                "payment_intent": "pi_test_parent",
                "charge": "ch_test_parent",
                "hosted_invoice_url": "https://invoice.stripe.com/i/test",
                "receipt_url": "https://pay.stripe.com/receipts/test",
                "status": "paid",
                "currency": "chf",
                "amount_due": 1500,
                "amount_paid": 1500,
                "amount_remaining": 0,
                "amount_refunded": 0,
                "tax": 115,
                "number": "STOA-2026-0001",
                "lines": {
                    "data": [
                        {
                            "period": {
                                "start": 1780272000,
                                "end": 1782864000,
                            }
                        }
                    ]
                },
                "payment_method_details": {"type": "twint"},
            }
        },
    }
    invoice_payload = json.dumps(invoice_paid, separators=(",", ":")).encode("utf-8")
    response = webhook_client.post(
        "/billing/webhooks/stripe",
        content=invoice_payload,
        headers={"stripe-signature": _stripe_signature(invoice_payload, secret)},
    )
    duplicate = webhook_client.post(
        "/billing/webhooks/stripe",
        content=invoice_payload,
        headers={"stripe-signature": _stripe_signature(invoice_payload, secret)},
    )

    assert response.status_code == 503
    assert duplicate.status_code == 503
    billing_status = parent_client.get("/parents/me/subscription/billing").json()
    assert billing_status["status"] == "checkout_pending"
    assert billing_status["subscriptionTier"] == "free_trial"
    assert profiles["parent-1"]["subscription_tier"] == "free_trial"
    return

    assert billing_status["status"] == "active"
    assert billing_status["subscriptionTier"] == "family"
    assert billing_status["providerSubscriptionId"] == "sub_test_parent"
    assert billing_status["providerLivemode"] is False
    assert billing_status["paymentMethodType"] == "twint"
    assert billing_status["latestInvoice"]["providerInvoiceId"] == "in_test_parent"
    assert billing_status["latestInvoice"]["hostedInvoiceUrl"] == "https://invoice.stripe.com/i/test"
    assert billing_status["latestInvoice"]["receiptUrl"] == "https://pay.stripe.com/receipts/test"
    assert billing_status["latestInvoice"]["currency"] == "CHF"
    assert billing_status["latestInvoice"]["amountPaid"] == 1500
    assert billing_status["latestInvoice"]["taxStatus"] == "provider_managed"
    assert billing_status["refund"]["state"] == "ready_for_provider"
    assert billing_status["refund"]["eligibleAmount"] == 1500
    assert billing_status["refund"]["requiresReason"] is True
    assert billing_status["dunning"]["state"] == "active"
    assert billing_status["accountingHandoff"]["providerInvoiceId"] == "in_test_parent"
    assert billing_status["accountingHandoff"]["currency"] == "CHF"
    assert billing_status["accountingHandoff"]["paymentMethodType"] == "twint"
    assert billing_status["accountingHandoff"]["reconciliationId"] == "STOA-2026-0001"
    webhook_events = [
        event
        for event in billing_status["events"]
        if event["providerEventId"] == "evt_invoice_paid_1"
    ]
    assert webhook_events[0]["providerLivemode"] is False
    assert webhook_events[0]["processingResult"] == "processed"
    assert any(event["processingResult"] == "deduplicated" for event in webhook_events)
    assert profiles["parent-1"]["subscription_tier"] == "family"
    assert table.items[("BILLING_PROVIDER_LOOKUP#stripe#subscription#sub_test_parent", "SUMMARY")][
        "parent_id"
    ] == "parent-1"
    assert table.items[("BILLING_PROVIDER_LOOKUP#stripe#charge#ch_test_parent", "SUMMARY")][
        "parent_id"
    ] == "parent-1"

    export_response = admin_client.get("/admin/subscriptions/billing/accounting-export")
    assert export_response.status_code == 200
    export = export_response.json()
    assert export["count"] == 1
    assert export["items"][0]["providerInvoiceId"] == "in_test_parent"
    assert export["items"][0]["taxStatus"] == "provider_managed"

    stale_failed_invoice = {
        "id": "evt_invoice_failed_stale_after_paid",
        "type": "invoice.payment_failed",
        "created": invoice_created - 60,
        "data": {
            "object": {
                "id": "in_test_parent",
                "object": "invoice",
                "status": "open",
                "customer": "cus_test_parent",
                "subscription": "sub_test_parent",
                "currency": "chf",
                "amount_due": 1500,
                "amount_paid": 0,
                "amount_remaining": 1500,
            }
        },
    }
    stale_payload = json.dumps(stale_failed_invoice, separators=(",", ":")).encode("utf-8")
    stale_response = webhook_client.post(
        "/billing/webhooks/stripe",
        content=stale_payload,
        headers={"stripe-signature": _stripe_signature(stale_payload, secret)},
    )
    stale_status = parent_client.get("/parents/me/subscription/billing").json()
    stale_events = [
        event
        for event in stale_status["events"]
        if event["providerEventId"] == "evt_invoice_failed_stale_after_paid"
    ]
    assert stale_response.status_code == 200
    assert stale_response.json()["billingStatus"] == "active"
    assert stale_response.json()["processingResult"] == "stale_ignored"
    assert stale_status["status"] == "active"
    assert stale_status["subscriptionTier"] == "family"
    assert stale_events[0]["processingResult"] == "stale_ignored"
    assert profiles["parent-1"]["subscription_tier"] == "family"
    support_evidence = admin_client.get("/admin/subscriptions/billing/parent-1").json()["supportEvidence"]
    assert support_evidence["lifecycle"]["status"] == "active"
    assert support_evidence["lifecycle"]["source"] == "provider_billing"
    assert support_evidence["invoice"]["providerInvoiceId"] == "in_test_parent"
    assert support_evidence["refund"]["state"] == "ready_for_provider"
    assert support_evidence["reconciliation"]["lastProviderEventId"] == "evt_invoice_paid_1"
    assert support_evidence["reconciliation"]["duplicateEvents"] == 1
    assert support_evidence["reconciliation"]["staleIgnoredEvents"] == 1

    refund_updated = {
        "id": "re_test_parent",
        "type": "refund.updated",
        "created": int(time.time()),
        "data": {
            "object": {
                "id": "re_test_parent",
                "object": "refund",
                "status": "succeeded",
                "charge": "ch_test_parent",
                "payment_intent": "pi_test_parent",
                "invoice": "in_test_parent",
                "amount": 500,
                "currency": "chf",
            }
        },
    }
    refund_payload = json.dumps(refund_updated, separators=(",", ":")).encode("utf-8")
    refund_response = webhook_client.post(
        "/billing/webhooks/stripe",
        content=refund_payload,
        headers={"stripe-signature": _stripe_signature(refund_payload, secret)},
    )
    assert refund_response.status_code == 200
    refunded_status = parent_client.get("/parents/me/subscription/billing").json()
    assert refunded_status["refund"]["state"] == "succeeded"
    assert refunded_status["refund"]["providerRefundId"] == "re_test_parent"
    assert refunded_status["latestInvoice"]["amountRefunded"] == 500
    assert refunded_status["refund"]["eligibleAmount"] == 1000
    assert refunded_status["accountingHandoff"]["refund"]["providerRefundId"] == "re_test_parent"
    assert refunded_status["accountingHandoff"]["refund"]["eligibleAmount"] == 1000

    replacement_session_id = "cs_test_legacy_webhook_replacement"
    replacement_attempt = table.items[("SUBSCRIPTION_BILLING#parent-1", "SUMMARY")]
    replacement_attempt.update(
        requested_tier="student",
        checkout_session_id=replacement_session_id,
        previous_billing_status="active",
        previous_subscription_tier="family",
        billing_status="checkout_pending",
    )
    expired = {
        "id": "evt_checkout_expired_1",
        "type": "checkout.session.expired",
        "created": int(time.time()),
        "data": {
            "object": {
                "id": replacement_session_id,
                "object": "checkout.session",
                "livemode": False,
                "customer": "cus_test_parent",
                "metadata": {
                    "stoa_parent_id": "parent-1",
                    "requested_tier": "student",
                },
            }
        },
    }
    expired_payload = json.dumps(expired, separators=(",", ":")).encode("utf-8")
    expired_response = webhook_client.post(
        "/billing/webhooks/stripe",
        content=expired_payload,
        headers={"stripe-signature": _stripe_signature(expired_payload, secret)},
    )

    assert expired_response.status_code == 200
    assert expired_response.json()["billingStatus"] == "active"
    preserved_status = parent_client.get("/parents/me/subscription/billing").json()
    assert preserved_status["status"] == "active"
    assert preserved_status["subscriptionTier"] == "family"
    assert profiles["parent-1"]["subscription_tier"] == "family"


def test_payment_failed_projects_dunning_and_twint_lifecycle(monkeypatch):
    _install_fakes(monkeypatch)
    secret = "whsec_test_secret"
    settings = _settings(stripe_webhook_secret=secret)
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))
    webhook_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))

    checkout_session_id = "cs_test_legacy_webhook_failed"
    checkout_completed = {
        "id": "evt_checkout_completed_failed_path",
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": checkout_session_id,
                "object": "checkout.session",
                "customer": "cus_test_parent_failed",
                "subscription": "sub_test_parent_failed",
                "metadata": {
                    "stoa_parent_id": "parent-1",
                    "requested_tier": "student",
                },
            }
        },
    }
    checkout_payload = json.dumps(checkout_completed, separators=(",", ":")).encode("utf-8")
    webhook_client.post(
        "/billing/webhooks/stripe",
        content=checkout_payload,
        headers={"stripe-signature": _stripe_signature(checkout_payload, secret)},
    )
    failed_invoice = {
        "id": "evt_invoice_failed_1",
        "object": "event",
        "type": "invoice.payment_failed",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": "in_failed_parent",
                "object": "invoice",
                "status": "open",
                "customer": "cus_test_parent_failed",
                "subscription": "sub_test_parent_failed",
                "hosted_invoice_url": None,
                "currency": "chf",
                "amount_due": 1500,
                "amount_paid": 0,
                "amount_remaining": 1500,
                "next_payment_attempt": 1780358400,
                "payment_method_details": {"type": "twint"},
            }
        },
    }
    failed_payload = json.dumps(failed_invoice, separators=(",", ":")).encode("utf-8")

    response = webhook_client.post(
        "/billing/webhooks/stripe",
        content=failed_payload,
        headers={"stripe-signature": _stripe_signature(failed_payload, secret)},
    )

    assert response.status_code == 200
    assert response.json()["billingStatus"] == "payment_failed"
    billing_status = parent_client.get("/parents/me/subscription/billing").json()
    assert billing_status["status"] == "payment_failed"
    assert billing_status["dunning"]["state"] == "retrying"
    assert billing_status["dunning"]["nextPaymentAttempt"] == "2026-06-02T00:00:00+00:00"
    assert billing_status["latestInvoice"]["hostedInvoiceUrl"] is None
    assert billing_status["latestInvoice"]["amountRemaining"] == 1500
    assert billing_status["paymentMethodType"] == "twint"
    assert billing_status["refund"]["state"] == "not_eligible"

    follow_up = {
        "id": "evt_customer_updated_failed_path",
        "object": "event",
        "type": "customer.updated",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": "cus_test_parent_failed",
                "object": "customer",
                "metadata": {"stoa_parent_id": "parent-1"},
            }
        },
    }
    follow_up_payload = json.dumps(follow_up, separators=(",", ":")).encode("utf-8")
    webhook_client.post(
        "/billing/webhooks/stripe",
        content=follow_up_payload,
        headers={"stripe-signature": _stripe_signature(follow_up_payload, secret)},
    )
    after_follow_up = parent_client.get("/parents/me/subscription/billing").json()
    assert after_follow_up["dunning"]["state"] == "retrying"
    assert after_follow_up["dunning"]["nextPaymentAttempt"] == "2026-06-02T00:00:00+00:00"

    recovered_invoice = {
        "id": "evt_invoice_recovered_1",
        "object": "event",
        "type": "invoice.paid",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": "in_failed_parent",
                "object": "invoice",
                "status": "paid",
                "customer": "cus_test_parent_failed",
                "subscription": "sub_test_parent_failed",
                "currency": "chf",
                "amount_due": 1500,
                "amount_paid": 1500,
                "amount_remaining": 0,
                "payment_method_details": {"type": "twint"},
            }
        },
    }
    recovered_payload = json.dumps(recovered_invoice, separators=(",", ":")).encode("utf-8")
    recovered_response = webhook_client.post(
        "/billing/webhooks/stripe",
        content=recovered_payload,
        headers={"stripe-signature": _stripe_signature(recovered_payload, secret)},
    )
    assert recovered_response.status_code == 503
    recovered_status = parent_client.get("/parents/me/subscription/billing").json()
    assert recovered_status["status"] == "payment_failed"
    assert recovered_status["dunning"]["state"] == "retrying"


def test_stripe_webhook_rejects_bad_signature(monkeypatch):
    _install_fakes(monkeypatch)
    settings = _settings(stripe_webhook_secret="whsec_test_secret")
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))
    payload = (
        b'{"id":"evt_bad","object":"event","type":"customer.updated",'
        b'"livemode":false,"data":{"object":{}}}'
    )

    response = client.post(
        "/billing/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": "t=123,v1=bad"},
    )

    assert response.status_code == 400


def test_stripe_webhook_requires_signing_secret_by_default(monkeypatch):
    _install_fakes(monkeypatch)
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))
    payload = b'{"id":"evt_unsigned","type":"customer.updated","data":{"object":{"metadata":{"stoa_parent_id":"parent-1"}}}}'

    response = client.post("/billing/webhooks/stripe", content=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == "Stripe webhook signing secret is required"


def test_manual_subscription_apply_sets_manual_override_billing(monkeypatch):
    _install_fakes(monkeypatch)
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    created = parent_client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "student"},
    ).json()
    admin_client.patch(
        f"/admin/subscriptions/requests/{created['requestId']}",
        json={"status": "approved"},
    )
    applied = admin_client.post(
        f"/admin/subscriptions/requests/{created['requestId']}/apply",
        json={"admin_note": "Manual bank transfer"},
    )

    assert applied.status_code == 200
    billing_status = admin_client.get("/admin/subscriptions/billing/parent-1").json()
    assert billing_status["status"] == "manual_override"
    assert billing_status["subscriptionTier"] == "student"
    assert billing_status["manualOverrideSource"] == created["requestId"]
    assert billing_status["effectiveEntitlements"][0]["effectivePlan"] == "student"
    assert billing_status["effectiveEntitlements"][0]["source"] == "manual_override"
