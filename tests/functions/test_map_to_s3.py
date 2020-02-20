from cdn_lambda.functions.map_to_s3.map_to_s3 import lambda_handler
import pytest
import mock
import json

TEST_PATH = "www.example.com/content/file.ext"
MOCKED_DT = "2020-02-17T15:38:05.864+00:00"
CONF_PATH = "cdn_lambda/functions/map_to_s3/map_to_s3.json"


@mock.patch("boto3.client")
@mock.patch("cdn_lambda.functions.map_to_s3.map_to_s3.datetime")
def test_map_to_s3(mocked_datetime, mocked_boto3_client):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "web_uri": {"S": TEST_PATH},
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                "object_key": {"S": "e4a3f2sum"},
            }
        ]
    }

    event = {"Records": [{"cf": {"request": {"uri": TEST_PATH}}}]}

    request = lambda_handler(event, context=None, conf_file=CONF_PATH)

    assert request == {"uri": "/e4a3f2sum"}


@mock.patch("boto3.client")
@mock.patch("cdn_lambda.functions.map_to_s3.map_to_s3.datetime")
def test_map_to_s3_no_item(mocked_datetime, mocked_boto3_client):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().query.return_value = {"Items": []}

    event = {"Records": [{"cf": {"request": {"uri": TEST_PATH}}}]}

    request = lambda_handler(event, context=None, conf_file=CONF_PATH)

    assert request == {"status": "404", "statusDescription": "Not Found"}


@mock.patch("boto3.client")
@mock.patch("cdn_lambda.functions.map_to_s3.map_to_s3.datetime")
def test_map_to_s3_invalid_item(mocked_datetime, mocked_boto3_client, caplog):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "web_uri": {"S": TEST_PATH},
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
            }
        ]
    }

    event = {"Records": [{"cf": {"request": {"uri": TEST_PATH}}}]}

    with pytest.raises(KeyError):
        lambda_handler(event, context=None, conf_file=CONF_PATH)

    assert (
        "Exception occurred while processing %s"
        % json.dumps(
            {
                "web_uri": {"S": TEST_PATH},
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
            }
        )
        in caplog.text
    )
