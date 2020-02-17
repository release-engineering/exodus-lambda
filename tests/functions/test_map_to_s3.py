from cdn_lambda.functions.map_to_s3 import lambda_handler
import os
import mock
import json

TEST_PATH = "www.example.com/content/file.ext"
MOCKED_DT = "2020-02-17T15:38:05.864+00:00"


@mock.patch("boto3.client")
@mock.patch("cdn_lambda.functions.map_to_s3.datetime")
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

    env_vars = {"DB_TABLE_NAME": "test_table", "DB_TABLE_REGION": "us-east-1"}
    event = {"Records": [{"cf": {"request": {"uri": TEST_PATH}}}]}

    with mock.patch.dict(os.environ, env_vars):
        request = lambda_handler(event, context=None)

    mocked_boto3_client().query.assert_called_with(
        TableName="test_table",
        Limit=1,
        ScanIndexForward=False,
        KeyConditionExpression="web_uri = :u and from_date <= :d",
        ExpressionAttributeValues={
            ":u": {"S": TEST_PATH},
            ":d": {"S": MOCKED_DT},
        },
    )

    assert request == {"uri": "e4a3f2sum"}

    mocked_boto3_client().query.assert_called_with(
        TableName="test_table",
        Limit=1,
        ScanIndexForward=False,
        KeyConditionExpression="web_uri = :u and from_date <= :d",
        ExpressionAttributeValues={
            ":u": {"S": TEST_PATH},
            ":d": {"S": MOCKED_DT},
        },
    )


@mock.patch("boto3.client")
@mock.patch("cdn_lambda.functions.map_to_s3.datetime")
def test_map_to_s3_no_item(mocked_datetime, mocked_boto3_client):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().query.return_value = {"Items": []}

    env_vars = {"DB_TABLE_NAME": "test_table", "DB_TABLE_REGION": "us-east-1"}
    event = {"Records": [{"cf": {"request": {"uri": TEST_PATH}}}]}

    with mock.patch.dict(os.environ, env_vars):
        request = lambda_handler(event, context=None)

    mocked_boto3_client().query.assert_called_with(
        TableName="test_table",
        Limit=1,
        ScanIndexForward=False,
        KeyConditionExpression="web_uri = :u and from_date <= :d",
        ExpressionAttributeValues={
            ":u": {"S": TEST_PATH},
            ":d": {"S": MOCKED_DT},
        },
    )

    assert request == {"status": "404", "statusDescription": "Not Found"}


@mock.patch("boto3.client")
@mock.patch("cdn_lambda.functions.map_to_s3.datetime")
def test_map_to_s3_invalid_item(mocked_datetime, mocked_boto3_client):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "web_uri": {"S": TEST_PATH},
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
            }
        ]
    }

    env_vars = {"DB_TABLE_NAME": "test_table", "DB_TABLE_REGION": "us-east-1"}
    event = {"Records": [{"cf": {"request": {"uri": TEST_PATH}}}]}

    with mock.patch.dict(os.environ, env_vars):
        request = lambda_handler(event, context=None)

    mocked_boto3_client().query.assert_called_with(
        TableName="test_table",
        Limit=1,
        ScanIndexForward=False,
        KeyConditionExpression="web_uri = :u and from_date <= :d",
        ExpressionAttributeValues={
            ":u": {"S": TEST_PATH},
            ":d": {"S": MOCKED_DT},
        },
    )

    err_msg = (
        "No 'object_key' found in %s",
        json.dumps(
            {
                "web_uri": {"S": TEST_PATH},
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
            }
        ),
    )

    assert request == {
        "status": "500",
        "statusDescription": "Internal Server Error",
        "body": {"error": err_msg},
    }
