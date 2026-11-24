"""What a request reads from the table is measured only while the switch is on (#610)."""

from __future__ import annotations

import logging

import boto3
import pytest
from boto3.dynamodb.conditions import Key
from botocore.stub import ANY, Stubber
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fakes.dynamodb import FakeTable
from stoa import config
from stoa.db import read_metering
from stoa.db import table as db_table
from stoa.main import app as stoa_app
from stoa.rule_violation import CorrelationMiddleware

LOGGER = "stoa.db.read_metering"


def _key() -> dict:
    # A fresh one each time: the table resource rewrites what it is handed.
    return {"PK": {"S": "USER#secret-id"}, "SK": {"S": "PROFILE"}}


def _client():
    return boto3.client("dynamodb", region_name="eu-central-2")


def _switch(on: bool) -> None:
    config.install(config.settings().model_copy(update={"dynamodb_read_metering": on}))


@pytest.fixture
def switched_on():
    _switch(True)
    yield
    config.install(None)


def _lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == LOGGER and "event_category=dynamodb_read_metering" in record.getMessage()
    ]


def _fields(line: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in line.split(" "))


# -- the hook on a boto3 client ---------------------------------------------------------


def test_a_read_inside_a_meter_asks_for_its_capacity_and_is_counted():
    client = _client()
    read_metering.attach(client)
    with Stubber(client) as stub:
        # The stub refuses a request whose parameters are not exactly these.
        stub.add_response(
            "get_item",
            {"ConsumedCapacity": {"TableName": "t", "CapacityUnits": 0.5}},
            {"TableName": "t", "Key": _key(), "ReturnConsumedCapacity": "TOTAL"},
        )
        stub.add_response(
            "query",
            {"Items": [], "ConsumedCapacity": {"TableName": "t", "CapacityUnits": 12.5}},
            {
                "TableName": "t",
                "KeyConditionExpression": "PK = :p",
                "ExpressionAttributeValues": {":p": {"S": "a"}},
                "ReturnConsumedCapacity": "TOTAL",
            },
        )
        with read_metering.measuring() as meter:
            client.get_item(TableName="t", Key=_key())
            client.query(
                TableName="t",
                KeyConditionExpression="PK = :p",
                ExpressionAttributeValues={":p": {"S": "a"}},
            )
        stub.assert_no_pending_responses()

    assert (meter.calls("GetItem"), meter.units("GetItem")) == (1, 0.5)
    assert (meter.calls("Query"), meter.units("Query")) == (1, 12.5)
    assert (meter.total_calls, meter.total_units) == (2, 13.0)


def test_a_batch_read_adds_up_the_capacity_of_every_table():
    client = _client()
    read_metering.attach(client)
    request = {"t": {"Keys": [_key()]}}
    with Stubber(client) as stub:
        stub.add_response(
            "batch_get_item",
            {
                "Responses": {},
                "ConsumedCapacity": [
                    {"TableName": "t", "CapacityUnits": 1.0},
                    {"TableName": "u", "CapacityUnits": 3.0},
                ],
            },
            {"RequestItems": request, "ReturnConsumedCapacity": "TOTAL"},
        )
        with read_metering.measuring() as meter:
            client.batch_get_item(RequestItems=request)

    assert (meter.calls("BatchGetItem"), meter.units("BatchGetItem")) == (1, 4.0)


def test_the_table_resource_is_measured_through_its_own_client():
    table = boto3.resource("dynamodb", region_name="eu-central-2").Table("t")
    read_metering.attach(table.meta.client)
    with Stubber(table.meta.client) as stub:
        stub.add_response(
            "scan",
            {
                "Items": [{"PK": {"S": "a"}}],
                "ConsumedCapacity": {"TableName": "t", "CapacityUnits": 128.0},
            },
            {"TableName": "t", "ReturnConsumedCapacity": "TOTAL"},
        )
        stub.add_response(
            "get_item",
            {"Item": _key(), "ConsumedCapacity": {"TableName": "t", "CapacityUnits": 1.0}},
            {"TableName": "t", "Key": ANY, "ReturnConsumedCapacity": "TOTAL"},
        )
        with read_metering.measuring() as meter:
            page = table.scan()
            row = table.get_item(Key={"PK": "USER#secret-id", "SK": "PROFILE"})

    # The rows come back as the resource always hands them out.
    assert page["Items"] == [{"PK": "a"}]
    assert row["Item"] == {"PK": "USER#secret-id", "SK": "PROFILE"}
    assert (meter.units("Scan"), meter.units("GetItem")) == (128.0, 1.0)


def test_outside_a_meter_a_hooked_client_sends_what_it_always_sent():
    client = _client()
    read_metering.attach(client)
    with Stubber(client) as stub:
        stub.add_response("get_item", {}, {"TableName": "t", "Key": _key()})
        client.get_item(TableName="t", Key=_key())
        stub.assert_no_pending_responses()


def test_a_write_is_never_asked_for_its_capacity():
    client = _client()
    read_metering.attach(client)
    with Stubber(client) as stub:
        stub.add_response("put_item", {}, {"TableName": "t", "Item": _key()})
        with read_metering.measuring() as meter:
            client.put_item(TableName="t", Item=_key())
        stub.assert_no_pending_responses()

    assert meter.total_calls == 0


def test_a_caller_that_chose_its_own_capacity_report_keeps_it():
    client = _client()
    read_metering.attach(client)
    with Stubber(client) as stub:
        stub.add_response(
            "get_item", {}, {"TableName": "t", "Key": _key(), "ReturnConsumedCapacity": "NONE"}
        )
        with read_metering.measuring() as meter:
            client.get_item(TableName="t", Key=_key(), ReturnConsumedCapacity="NONE")

    # Counted as a call; nothing was reported, so nothing is added.
    assert (meter.calls("GetItem"), meter.total_units) == (1, 0.0)


def test_a_refused_read_is_counted_without_capacity():
    client = _client()
    read_metering.attach(client)
    with Stubber(client) as stub:
        stub.add_client_error("get_item", service_error_code="ValidationException")
        with read_metering.measuring() as meter, pytest.raises(client.exceptions.ClientError):
            client.get_item(TableName="t", Key=_key())

    assert (meter.calls("GetItem"), meter.total_units) == (1, 0.0)


@pytest.mark.parametrize(
    ("consumed", "units"),
    [
        ({"CapacityUnits": 2.5}, 2.5),
        ({"CapacityUnits": 3}, 3.0),
        ([{"CapacityUnits": 1.5}, {"CapacityUnits": 1.5}], 3.0),
        (None, 0.0),
        ({"TableName": "t"}, 0.0),
        ({"CapacityUnits": "many"}, 0.0),
        ("unreadable", 0.0),
    ],
)
def test_consumed_units_reads_only_what_dynamodb_reports(consumed, units):
    assert read_metering.consumed_units(consumed) == units


# -- the gateway attaches it only while the switch is on --------------------------------


def _hooked(client) -> bool:
    """Whether a read through `client`, inside a meter, asks for its capacity."""
    expected = {"TableName": "t", "Key": ANY}
    with Stubber(client) as stub:
        stub.add_response("get_item", {}, {**expected, "ReturnConsumedCapacity": "TOTAL"})
        with read_metering.measuring():
            try:
                client.get_item(TableName="t", Key=_key())
            except Exception:  # noqa: BLE001 - the stub refused the unhooked request
                return False
    return True


def test_with_the_switch_off_the_gateway_builds_unhooked_clients():
    db_table.install(None)
    assert config.settings().dynamodb_read_metering is False
    assert not _hooked(db_table.client())
    assert not _hooked(db_table.table().meta.client)


def test_with_the_switch_on_the_gateway_hooks_its_client_and_its_table(switched_on):
    db_table.install(None)
    assert _hooked(db_table.client())
    assert _hooked(db_table.table().meta.client)


# -- one line per request ---------------------------------------------------------------


def _application(boto_client=None) -> FastAPI:
    application = FastAPI()
    application.add_middleware(CorrelationMiddleware)
    application.add_middleware(read_metering.ReadMeteringMiddleware)

    @application.get("/things/{thing_id}")
    def thing(thing_id: str):
        # A synchronous route: it runs on a worker thread, as most routes do.
        db_table.get(Key={"PK": f"THING#{thing_id}", "SK": "META"})
        db_table.rows("query", KeyConditionExpression=Key("PK").eq(f"THING#{thing_id}"))
        if boto_client is not None:
            boto_client.get_item(TableName="t", Key=_key())
            boto_client.query(TableName="t", KeyConditionExpression="PK = :p")
            boto_client.query(TableName="t", KeyConditionExpression="PK = :p")
        return {"id": thing_id}

    @application.get("/async-things/{thing_id}")
    async def async_thing(thing_id: str):
        if boto_client is not None:
            boto_client.scan(TableName="t")
        return {"id": thing_id}

    return application


def _stubbed_reads(stub: Stubber, *, asked: bool) -> None:
    extra = {"ReturnConsumedCapacity": "TOTAL"} if asked else {}
    consumed = lambda units: (  # noqa: E731
        {"ConsumedCapacity": {"TableName": "t", "CapacityUnits": units}} if asked else {}
    )
    stub.add_response("get_item", consumed(0.5), {"TableName": "t", "Key": _key(), **extra})
    for units in (40.0, 60.25):
        stub.add_response(
            "query",
            {"Items": [], **consumed(units)},
            {"TableName": "t", "KeyConditionExpression": "PK = :p", **extra},
        )


def test_a_request_logs_one_line_with_its_reads(switched_on, caplog):
    table = FakeTable()
    db_table.install(table)
    client = _client()
    read_metering.attach(client)
    caplog.set_level(logging.INFO, logger=LOGGER)

    with Stubber(client) as stub:
        _stubbed_reads(stub, asked=True)
        response = TestClient(_application(client)).get("/things/secret-id-123?token=abc")
        stub.assert_no_pending_responses()

    assert response.status_code == 200
    (line,) = _lines(caplog)
    fields = _fields(line)
    assert fields == {
        "event_category": "dynamodb_read_metering",
        "route": "/things/{thing_id}",
        "method": "GET",
        "status": "200",
        "rcu": "100.75",
        "read_calls": "3",
        "wall_ms": fields["wall_ms"],
        "query_calls": "2",
        "query_rcu": "100.25",
        "scan_calls": "0",
        "scan_rcu": "0",
        "get_item_calls": "1",
        "get_item_rcu": "0.5",
        "batch_get_item_calls": "0",
        "batch_get_item_rcu": "0",
        "transact_get_items_calls": "0",
        "transact_get_items_rcu": "0",
    }
    assert int(fields["wall_ms"]) >= 0
    # Nothing the caller typed, and nothing a row holds.
    assert "secret-id" not in line and "abc" not in line and "THING#" not in line
    # The double is read exactly as before: it is not a boto3 client.
    assert [name for name, _ in table.requests] == ["get_item", "query"]
    assert all("ReturnConsumedCapacity" not in request for _, request in table.requests)


def test_reads_of_an_async_route_are_counted_too(switched_on, caplog):
    client = _client()
    read_metering.attach(client)
    caplog.set_level(logging.INFO, logger=LOGGER)

    with Stubber(client) as stub:
        stub.add_response(
            "scan",
            {"Items": [], "ConsumedCapacity": {"TableName": "t", "CapacityUnits": 512.0}},
            {"TableName": "t", "ReturnConsumedCapacity": "TOTAL"},
        )
        TestClient(_application(client)).get("/async-things/7")

    fields = _fields(_lines(caplog)[0])
    assert (fields["route"], fields["scan_calls"], fields["rcu"]) == (
        "/async-things/{thing_id}",
        "1",
        "512",
    )


def test_each_request_is_measured_by_itself(switched_on, caplog):
    client = _client()
    read_metering.attach(client)
    caplog.set_level(logging.INFO, logger=LOGGER)
    browser = TestClient(_application(client))

    with Stubber(client) as stub:
        _stubbed_reads(stub, asked=True)
        browser.get("/things/1")
    # The second request reads only the double, which reports no capacity.
    second = TestClient(_application()).get("/things/2")

    assert second.status_code == 200
    first_line, second_line = _lines(caplog)
    assert _fields(first_line)["rcu"] == "100.75"
    assert (_fields(second_line)["rcu"], _fields(second_line)["read_calls"]) == ("0", "0")


def test_a_request_that_matches_no_route_does_not_log_its_path(switched_on, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)

    response = TestClient(_application()).get("/nowhere/secret-id-123")

    assert response.status_code == 404
    (line,) = _lines(caplog)
    assert (_fields(line)["route"], _fields(line)["status"]) == ("unmatched", "404")
    assert "secret-id" not in line and "nowhere" not in line


def test_a_failing_route_is_still_logged(switched_on, caplog):
    application = FastAPI()
    application.add_middleware(read_metering.ReadMeteringMiddleware)

    @application.post("/broken/{thing_id}")
    def broken(thing_id: str):
        raise RuntimeError("no")

    caplog.set_level(logging.INFO, logger=LOGGER)
    response = TestClient(application, raise_server_exceptions=False).post("/broken/9")

    assert response.status_code == 500
    fields = _fields(_lines(caplog)[0])
    assert (fields["route"], fields["method"], fields["status"]) == (
        "/broken/{thing_id}",
        "POST",
        "500",
    )


def test_with_the_switch_off_nothing_is_asked_and_nothing_is_logged(caplog):
    table = FakeTable()
    db_table.install(table)
    client = _client()
    # Even a hooked client sends its plain request: no meter is ever opened.
    read_metering.attach(client)
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    assert config.settings().dynamodb_read_metering is False

    with Stubber(client) as stub:
        _stubbed_reads(stub, asked=False)
        response = TestClient(_application(client)).get("/things/1")
        stub.assert_no_pending_responses()

    assert response.status_code == 200
    assert [record for record in caplog.records if record.name == LOGGER] == []
    assert all("ReturnConsumedCapacity" not in request for _, request in table.requests)


def test_the_application_measures_the_whole_request():
    order = [item.cls for item in stoa_app.user_middleware]
    # user_middleware lists the outermost first: the time logged covers the
    # correlation middleware and everything inside it.
    assert order.index(read_metering.ReadMeteringMiddleware) < order.index(CorrelationMiddleware)


def test_the_switch_is_off_unless_the_environment_turns_it_on(monkeypatch):
    monkeypatch.delenv("DYNAMODB_READ_METERING", raising=False)
    assert config.Settings(_env_file=None).dynamodb_read_metering is False
    monkeypatch.setenv("DYNAMODB_READ_METERING", "true")
    assert config.Settings(_env_file=None).dynamodb_read_metering is True
