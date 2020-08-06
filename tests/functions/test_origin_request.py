import json
import logging
import urllib

import pytest

import mock
from exodus_lambda.functions.origin_request import OriginRequest
from test_utils.utils import generate_test_config

TEST_PATH = "/origin/rpms/repo/ver/dir/filename.ext"
MOCKED_DT = "2020-02-17T15:38:05.864+00:00"
CONF_PATH = "configuration/lambda_config.json"
TEST_CONF = generate_test_config(CONF_PATH)


@pytest.mark.parametrize(
    "req_uri, real_uri, content_type",
    [
        (
            "/origin/rpm/repo/ver/dir/filename.ext",
            "/origin/rpms/repo/ver/dir/filename.ext",
            "text/plain",
        ),
        (
            "/content/origin/repo/ver/dir/filename.ext",
            "/origin/repo/ver/dir/filename.ext",
            "text/plain",
        ),
        (
            "/content/origin/rpm/repo/ver/dir/filename.ext",
            "/origin/rpms/repo/ver/dir/filename.ext",
            "text/plain",
        ),
        (
            "/content/dist/rhel/rhui/some/repo/somefile.ext",
            "/content/dist/rhel/some/repo/somefile.ext",
            "text/plain",
        ),
        (
            "/content/dist/rhel/rhui/some/listing",
            "/content/dist/rhel/rhui/some/listing",
            "text/plain",
        ),
        (
            "/content/origin/repo/ver/origin/rpm/filename.ext",
            "/origin/repo/ver/origin/rpm/filename.ext",
            "text/plain",
        ),
        (
            "/origin/rpms/repo/ver/dir/filename.ext",
            "/origin/rpms/repo/ver/dir/filename.ext",
            "text/plain",
        ),
    ],
    ids=[
        "/origin/rpm/",
        "content/origin",
        "content/origin/rpm",
        "rhui",
        "rhui listing exception",
        "multiple alias keywords",
        "no alias keywords",
    ],
)
@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request(
    mocked_datetime,
    mocked_boto3_client,
    req_uri,
    real_uri,
    content_type,
    caplog,
):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "web_uri": {"S": real_uri},
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                "object_key": {"S": "e4a3f2sum"},
                "content_type": {"S": content_type},
            }
        ]
    }

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(conf_file=TEST_CONF).handler(
            event, context=None
        )

    assert "Item found for '%s'" % real_uri in caplog.text

    assert request == {
        "uri": "/e4a3f2sum",
        "querystring": urllib.parse.urlencode(
            {"response-content-type": content_type}
        ),
        "headers": {
            "exodus-original-uri": [
                {"key": "exodus-original-uri", "value": req_uri}
            ]
        },
    }


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_no_item(mocked_datetime, mocked_boto3_client, caplog):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().query.return_value = {"Items": []}

    event = {"Records": [{"cf": {"request": {"uri": TEST_PATH}}}]}

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(conf_file=TEST_CONF).handler(
            event, context=None
        )

    assert request == {"status": "404", "statusDescription": "Not Found"}
    assert "No item found for '%s'" % TEST_PATH in caplog.text


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_invalid_item(
    mocked_datetime, mocked_boto3_client, caplog
):
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
        request = OriginRequest(conf_file=TEST_CONF).handler(
            event, context=None
        )

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
