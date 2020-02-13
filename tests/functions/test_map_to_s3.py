from cdn_lambda.functions.map_to_s3 import lambda_handler
import os
import mock
import json


@mock.patch("boto3.client")
@mock.patch("cdn_lambda.functions.map_to_s3.datetime")
def test_map_to_s3(mocked_datetime, mocked_boto3_client):
    mocked_datetime.utcnow.return_value = "2020-02-12 20:55:06.372878"
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "web_uri": {"S": "www.example.com/content/file.ext"},
                "from_date": {"S": "2020-02-12 21:02:59.097169"},
                "object_key": {"S": "e4a3f2sum"},
            }
        ]
    }

    env_vars = {"DB_TABLE_NAME": "test_table", "DB_TABLE_REGION": "us-east-1"}
    event = {
        "Records": [
            {"cf": {"request": {"uri": "www.example.com/content/file.ext"}}}
        ]
    }

    with mock.patch.dict(os.environ, env_vars):
        request = lambda_handler(event, context=None)

    mocked_boto3_client().query.assert_called_with(
        TableName="test_table",
        Limit=1,
        ScanIndexForward=False,
        KeyConditionExpression="web_uri = :u and from_date <= :d",
        ExpressionAttributeValues={
            ":u": {"S": "www.example.com/content/file.ext"},
            ":d": {"S": "2020-02-12 20:55:06.372878"},
        },
    )

    assert request == {"uri": "e4a3f2sum"}

    mocked_boto3_client().query.assert_called_with(
        TableName="test_table",
        Limit=1,
        ScanIndexForward=False,
        KeyConditionExpression="web_uri = :u and from_date <= :d",
        ExpressionAttributeValues={
            ":u": {"S": "www.example.com/content/file.ext"},
            ":d": {"S": "2020-02-12 20:55:06.372878"},
        },
    )


@mock.patch("boto3.client")
@mock.patch("cdn_lambda.functions.map_to_s3.datetime")
def test_map_to_s3_no_item(mocked_datetime, mocked_boto3_client):
    mocked_datetime.utcnow.return_value = "2020-02-12 20:55:06.372878"
    mocked_boto3_client().query.return_value = {"Items": []}

    env_vars = {"DB_TABLE_NAME": "test_table", "DB_TABLE_REGION": "us-east-1"}
    event = {
        "Records": [
            {"cf": {"request": {"uri": "www.example.com/content/file.ext"}}}
        ]
    }

    with mock.patch.dict(os.environ, env_vars):
        request = lambda_handler(event, context=None)

    mocked_boto3_client().query.assert_called_with(
        TableName="test_table",
        Limit=1,
        ScanIndexForward=False,
        KeyConditionExpression="web_uri = :u and from_date <= :d",
        ExpressionAttributeValues={
            ":u": {"S": "www.example.com/content/file.ext"},
            ":d": {"S": "2020-02-12 20:55:06.372878"},
        },
    )

    assert request == {"status": "404", "statusDescription": "Not Found"}


@mock.patch("boto3.client")
@mock.patch("cdn_lambda.functions.map_to_s3.datetime")
def test_map_to_s3_invalid_item(mocked_datetime, mocked_boto3_client):
    mocked_datetime.utcnow.return_value = "2020-02-12 20:55:06.372878"
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "web_uri": {"S": "www.example.com/content/file.ext"},
                "from_date": {"S": "2020-02-12 21:02:59.097169"},
            }
        ]
    }

    env_vars = {"DB_TABLE_NAME": "test_table", "DB_TABLE_REGION": "us-east-1"}
    event = {
        "Records": [
            {"cf": {"request": {"uri": "www.example.com/content/file.ext"}}}
        ]
    }

    with mock.patch.dict(os.environ, env_vars):
        request = lambda_handler(event, context=None)

    mocked_boto3_client().query.assert_called_with(
        TableName="test_table",
        Limit=1,
        ScanIndexForward=False,
        KeyConditionExpression="web_uri = :u and from_date <= :d",
        ExpressionAttributeValues={
            ":u": {"S": "www.example.com/content/file.ext"},
            ":d": {"S": "2020-02-12 20:55:06.372878"},
        },
    )

    err_msg = (
        "No 'object_key' found in %s",
        json.dumps(
            {
                "web_uri": {"S": "www.example.com/content/file.ext"},
                "from_date": {"S": "2020-02-12 21:02:59.097169"},
            }
        ),
    )

    assert request == {
        "status": "500",
        "statusDescription": "Internal Server Error",
        "body": {"error": err_msg},
    }
