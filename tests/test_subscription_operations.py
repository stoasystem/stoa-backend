import hashlib
import hmac
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from botocore.exceptions import ClientError

from stoa.config import Settings, get_settings
from stoa.deps import get_current_user
from stoa.routers import admin, billing, parents
from stoa.services import subscription_service


class FakeTable:
    def __init__(self):
        self.items = {}
        self.scan_pages = []

    def put_item(self, Item):
        self.items[(Item["PK"], Item["SK"])] = dict(Item)

    def get_item(self, Key):
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
        sk_prefix = _condition_value(kwargs.get("KeyConditionExpression"), "SK")
        events = [
            dict(item)
            for (item_pk, sk), item in self.items.items()
            if item_pk == expected_pk and sk.startswith(sk_prefix or "EVENT#")
        ]
        return {"Items": events}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues, ExpressionAttributeNames=None):
        item = self.items.setdefault((Key["PK"], Key["SK"]), {"PK": Key["PK"], "SK": Key["SK"]})
        names = ExpressionAttributeNames or {}

        if names:
            assignments = UpdateExpression.removeprefix("SET ").split(",")
            for assignment in assignments:
                alias, value_alias = [part.strip() for part in assignment.split("=")]
                field = names[alias]
                item[field] = ExpressionAttributeValues[value_alias]
            return

        assignments = UpdateExpression.removeprefix("SET ").split(",")
        for assignment in assignments:
            field, value_alias = [part.strip() for part in assignment.split("=")]
            item[field] = ExpressionAttributeValues[value_alias]

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

    def _check_transaction_operation(self, operation):
        if "Put" in operation:
            put = operation["Put"]
            key = (put["Item"]["PK"], put["Item"]["SK"])
            if put.get("ConditionExpression") == "attribute_not_exists(PK)" and key in self.items:
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


def _settings(**overrides) -> Settings:
    return Settings(cognito_user_pool_id="pool", s3_images_bucket="images", **overrides)


def _app_for_user(user: dict, settings: Settings | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(parents.router, prefix="/parents")
    app.include_router(admin.router, prefix="/admin")
    app.include_router(billing.router, prefix="/billing")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_settings] = lambda: settings or _settings()
    return app


def _profiles():
    return {
        "parent-1": {
            "user_id": "parent-1",
            "email": "parent@example.com",
            "role": "parent",
            "subscription_tier": "free",
        },
        "admin-1": {
            "user_id": "admin-1",
            "email": "admin@example.com",
            "role": "admin",
            "subscription_tier": "premium",
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

    def get_user(user_id):
        return profiles.get(user_id)

    def update_item(Key, UpdateExpression, ExpressionAttributeValues, ExpressionAttributeNames=None):
        if Key["PK"].startswith("USER#") and Key["SK"] == "PROFILE":
            user_id = Key["PK"].removeprefix("USER#")
            profiles.setdefault(
                user_id,
                {"user_id": user_id, "role": "parent", "subscription_tier": "free"},
            )
            if ":tier" in ExpressionAttributeValues:
                profiles[user_id]["subscription_tier"] = ExpressionAttributeValues[":tier"]
            return
        return table_update_item(
            Key=Key,
            UpdateExpression=UpdateExpression,
            ExpressionAttributeValues=ExpressionAttributeValues,
            ExpressionAttributeNames=ExpressionAttributeNames,
        )

    table.update_item = update_item
    monkeypatch.setattr(subscription_service, "get_table", lambda: table)
    monkeypatch.setattr(subscription_service.user_repo, "get_user", get_user)
    monkeypatch.setattr(parents.user_repo, "get_user", get_user)
    return table, profiles


def test_parent_can_view_plan_options(monkeypatch):
    _install_fakes(monkeypatch)
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))

    response = client.get("/parents/me/subscription")

    assert response.status_code == 200
    body = response.json()
    assert body["currentTier"] == "free"
    assert body["plans"]["standard"]["dailyAiQuestionLimit"] == 30
    assert body["pendingRequest"] is None
    assert body["billing"]["status"] == "none"


def test_parent_can_create_subscription_request_once(monkeypatch):
    _install_fakes(monkeypatch)
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))

    response = client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "standard", "parentNote": "Please upgrade"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "requested"
    assert body["requestType"] == "upgrade"
    assert body["requestedTier"] == "standard"
    assert body["history"][0]["eventType"] == "requested"

    duplicate = client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "premium"},
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
        json={"requestType": "upgrade", "requestedTier": "standard"},
    ).json()
    request_id = created["requestId"]

    approved = admin_client.patch(
        f"/admin/subscriptions/requests/{request_id}",
        json={"status": "approved", "admin_note": "Bank transfer received"},
    )

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert profiles["parent-1"]["subscription_tier"] == "free"

    applied = admin_client.post(
        f"/admin/subscriptions/requests/{request_id}/apply",
        json={"admin_note": "Applied manually"},
    )

    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert profiles["parent-1"]["subscription_tier"] == "standard"
    assert table.items


def test_admin_list_filters_and_invalid_apply(monkeypatch):
    _install_fakes(monkeypatch)
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    created = parent_client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "standard"},
    ).json()

    listed = admin_client.get(
        "/admin/subscriptions/requests",
        params={"status": "requested", "requested_tier": "standard", "parent_id": "parent-1"},
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
        json={"requestType": "upgrade", "requestedTier": "standard"},
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
        json={"requestType": "upgrade", "requestedTier": "standard"},
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
        json={"requestType": "upgrade", "requestedTier": "standard"},
    ).json()
    admin_client.patch(
        f"/admin/subscriptions/requests/{first['requestId']}",
        json={"status": "cancelled", "admin_note": "Parent changed plans"},
    )
    second = parent_client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "premium"},
    ).json()

    response = admin_client.get(f"/admin/subscriptions/requests/{first['requestId']}")

    assert response.status_code == 200
    history = response.json()["history"]
    assert {event["eventType"] for event in history} == {"requested", "cancelled"}
    assert second["requestId"] not in str(history)


def test_parent_can_create_checkout_session_and_admin_can_inspect_billing(monkeypatch):
    _install_fakes(monkeypatch)
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    response = client.post(
        "/parents/me/subscription/checkout",
        json={"requestedTier": "standard"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["provider"] == "stripe"
    assert body["mode"] == "test"
    assert body["billingStatus"] == "checkout_pending"
    assert body["checkoutUrl"].startswith("https://checkout.stripe.com/c/pay/cs_test_")

    subscription = client.get("/parents/me/subscription").json()
    assert subscription["billing"]["status"] == "checkout_pending"
    assert subscription["billing"]["requestedTier"] == "standard"

    admin_response = admin_client.get("/admin/subscriptions/billing")
    assert admin_response.status_code == 200
    assert admin_response.json()["count"] == 1
    assert admin_response.json()["items"][0]["parentId"] == "parent-1"


def test_stripe_webhook_completion_activates_subscription_idempotently(monkeypatch):
    _install_fakes(monkeypatch)
    secret = "whsec_test_secret"
    settings = _settings(stripe_webhook_secret=secret)
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))
    webhook_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))

    checkout = parent_client.post(
        "/parents/me/subscription/checkout",
        json={"requestedTier": "premium"},
    ).json()
    event = {
        "id": "evt_checkout_completed_1",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "data": {
            "object": {
                "id": checkout["checkoutSessionId"],
                "object": "checkout.session",
                "customer": "cus_test_parent",
                "subscription": "sub_test_parent",
                "client_reference_id": "parent-1",
                "metadata": {"stoa_parent_id": "parent-1", "requested_tier": "premium"},
            }
        },
    }
    payload = json.dumps(event, separators=(",", ":")).encode("utf-8")

    response = webhook_client.post(
        "/billing/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": _stripe_signature(payload, secret)},
    )
    duplicate = webhook_client.post(
        "/billing/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": _stripe_signature(payload, secret)},
    )

    assert response.status_code == 200
    assert response.json()["billingStatus"] == "active"
    assert duplicate.status_code == 200
    assert duplicate.json()["deduplicated"] is True
    billing_status = parent_client.get("/parents/me/subscription/billing").json()
    assert billing_status["status"] == "active"
    assert billing_status["subscriptionTier"] == "premium"
    assert billing_status["providerSubscriptionId"] == "sub_test_parent"


def test_stripe_webhook_rejects_bad_signature(monkeypatch):
    _install_fakes(monkeypatch)
    settings = _settings(stripe_webhook_secret="whsec_test_secret")
    client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}, settings))
    payload = b'{"id":"evt_bad","type":"customer.updated","data":{"object":{}}}'

    response = client.post(
        "/billing/webhooks/stripe",
        content=payload,
        headers={"stripe-signature": "t=123,v1=bad"},
    )

    assert response.status_code == 400


def test_manual_subscription_apply_sets_manual_override_billing(monkeypatch):
    _install_fakes(monkeypatch)
    parent_client = TestClient(_app_for_user({"sub": "parent-1", "role": "parent"}))
    admin_client = TestClient(_app_for_user({"sub": "admin-1", "role": "admin"}))

    created = parent_client.post(
        "/parents/me/subscription/requests",
        json={"requestType": "upgrade", "requestedTier": "standard"},
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
    assert billing_status["subscriptionTier"] == "standard"
    assert billing_status["manualOverrideSource"] == created["requestId"]
