import pytest

from exodus_lambda.functions.db import QueryHelper


class DynamoDbBrokenClient:
    # A DynamoDb client for which all queries fail.

    def __init__(self, service, region_name, *args, **kwargs):
        assert service == "dynamodb"
        self._region = region_name

    def query(self, *args, **kwargs):
        raise RuntimeError(f"error from {self._region}")


def test_default_regions(caplog: pytest.LogCaptureFixture):
    """QueryHelper applies reasonable default if region config is missing"""
    db = QueryHelper({}, endpoint_url="https://aws.example.com/")

    # It should succeed...
    assert db._regions("my-table") == ["us-east-1"]

    # But should also warn about this
    assert (
        "No config for my-table, applying default regions" in caplog.messages
    )


def test_all_regions_fail(monkeypatch: pytest.MonkeyPatch):
    """Exceptions propagate correctly if queries fail in every configured region."""

    db = QueryHelper(
        {
            "table": {
                "name": "test",
                "available_regions": ["region1", "region2", "region3"],
            }
        },
        None,
    )

    monkeypatch.setattr("boto3.client", DynamoDbBrokenClient)

    # It should raise an exception
    with pytest.raises(BaseException) as excinfo:
        db.query(TableName="test")

    # Check the raised exception...
    exc = excinfo.value

    # The failure from every region should be represented
    # via chained exceptions.
    assert str(exc) == "error from region3"

    assert exc.__cause__
    assert str(exc.__cause__) == "error from region2"

    assert exc.__cause__.__cause__
    assert str(exc.__cause__.__cause__) == "error from region1"

    assert exc.__cause__.__cause__.__cause__ is None
