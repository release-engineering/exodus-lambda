from exodus_lambda.functions.map_to_s3.map_to_s3 import LambdaClient
import pytest
import mock
import json

TEST_PATH = "/origin/rpms/repo/ver/dir/filename.ext"
MOCKED_DT = "2020-02-17T15:38:05.864+00:00"
CONF_PATH = "exodus_lambda/functions/lambda_config.json"


@pytest.mark.parametrize(
    "req_uri, real_uri",
    [
        (
            "/origin/rpm/repo/ver/dir/filename.ext",
            "/origin/rpms/repo/ver/dir/filename.ext",
        ),
        (
            "/content/origin/repo/ver/dir/filename.ext",
            "/origin/repo/ver/dir/filename.ext",
        ),
        (
            "/content/origin/rpm/repo/ver/dir/filename.ext",
            "/origin/rpms/repo/ver/dir/filename.ext",
        ),
        (
            "/content/origin/repo/ver/origin/rpm/filename.ext",
            "/origin/repo/ver/origin/rpm/filename.ext",
        ),
        (
            "/origin/rpms/repo/ver/dir/filename.ext",
            "/origin/rpms/repo/ver/dir/filename.ext",
        ),
    ],
    ids=[
        "/origin/rpm/",
        "content/origin",
        "content/origin/rpm",
        "multiple alias keywords",
        "no alias keywords",
    ],
)
@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.map_to_s3.map_to_s3.datetime")
def test_map_to_s3(mocked_datetime, mocked_boto3_client, req_uri, real_uri):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "web_uri": {"S": real_uri},
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                "object_key": {"S": "e4a3f2sum"},
            }
        ]
    }

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}

    request = LambdaClient(conf_file=CONF_PATH).handler(event, context=None)

    assert request == {
        "uri": "/e4a3f2sum",
        "headers": {
            "exodus-original-uri": [
                {"key": "exodus-original-uri", "value": req_uri}
            ]
        },
    }


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.map_to_s3.map_to_s3.datetime")
def test_map_to_s3_no_item(mocked_datetime, mocked_boto3_client):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().query.return_value = {"Items": []}

    event = {"Records": [{"cf": {"request": {"uri": TEST_PATH}}}]}

    request = LambdaClient(conf_file=CONF_PATH).handler(event, context=None)

    assert request == {"status": "404", "statusDescription": "Not Found"}


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.map_to_s3.map_to_s3.datetime")
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
        LambdaClient(conf_file=CONF_PATH).handler(event, context=None)

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
