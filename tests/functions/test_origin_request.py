import json
import logging
import urllib

import mock
import pytest

from exodus_lambda.functions.origin_request import OriginRequest

from ..test_utils.utils import generate_test_config, mock_definitions

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
            "/content/dist/rhel/rhui/server/7/listing",
            "/content/dist/rhel/rhui/server/7/listing",
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
        (
            "/content/dist/rhel/server/7/7Server/test.ext",
            "/content/dist/rhel/server/7/7.9/test.ext",
            "text/plain",
        ),
        (
            "/content/dist/rhel/rhui/server/7/7Server/file.ext",
            "/content/dist/rhel/server/7/7.9/file.ext",
            "text/plain",
        ),
    ],
    ids=[
        "/origin/rpm/",
        "content/origin",
        "content/origin/rpm",
        "rhui",
        "listing",
        "multiple alias keywords",
        "no alias keywords",
        "releasever alias",
        "layered rhui, releasever alias",
    ],
)
@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request(
    mocked_datetime,
    mocked_cache,
    mocked_boto3_client,
    req_uri,
    real_uri,
    content_type,
    caplog,
):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}
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
        request = OriginRequest(
            conf_file=TEST_CONF,
        ).handler(event, context=None)

    if req_uri.endswith("/listing"):
        assert "Handling listing request" in caplog.text
        assert request["body"]
    else:
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
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_no_item(
    mocked_datetime, mocked_cache, mocked_boto3_client, caplog
):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}
    mocked_boto3_client().query.return_value = {"Items": []}

    event = {"Records": [{"cf": {"request": {"uri": TEST_PATH}}}]}

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(conf_file=TEST_CONF).handler(
            event, context=None
        )

    assert request == {"status": "404", "statusDescription": "Not Found"}
    assert "No item found for '%s'" % TEST_PATH in caplog.text


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_invalid_item(
    mocked_datetime, mocked_cache, mocked_boto3_client, caplog
):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}
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
        OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

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


@mock.patch("boto3.client")
def test_origin_request_definitions(mocked_boto3_client):
    mocked_defs = mock_definitions()
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                "config_id": {"S": "exodus-config"},
                "config": {"S": json.dumps(mocked_defs)},
            }
        ]
    }

    assert mocked_defs == OriginRequest(conf_file=TEST_CONF).definitions


@pytest.mark.parametrize(
    "cur_time, count", [(1741221.281833067, 2), (1741025.281833067, 1)]
)
@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.time.monotonic")
def test_origin_request_definitions_cache(
    mocked_time, mocked_boto3_client, cur_time, count
):
    mocked_defs = mock_definitions()
    mocked_time.return_value = 1741021.281833067
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                "config_id": {"S": "exodus-config"},
                "config": {"S": json.dumps(mocked_defs)},
            }
        ]
    }

    obj = OriginRequest(conf_file=TEST_CONF)
    obj.definitions
    assert obj._cache.currsize == 1  # pylint:disable=protected-access

    mocked_time.return_value = cur_time
    obj.definitions
    assert mocked_boto3_client().query.call_count == count


@pytest.mark.parametrize(
    "req_uri, real_uri",
    [
        (
            "/content/dist/rhel/some/filename.iso",
            "/content/dist/rhel/some/filename.iso",
        ),
    ],
    ids=[
        "no content_type",
    ],
)
@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_no_content_type(
    mocked_datetime,
    mocked_cache,
    mocked_boto3_client,
    req_uri,
    real_uri,
    caplog,
):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}
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

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(
            conf_file=TEST_CONF,
        ).handler(event, context=None)

    assert "Item found for '%s'" % real_uri in caplog.text

    assert request == {
        "uri": "/e4a3f2sum",
        "querystring": urllib.parse.urlencode(
            {"response-content-type": "application/octet-stream"}
        ),
        "headers": {
            "exodus-original-uri": [
                {"key": "exodus-original-uri", "value": req_uri}
            ]
        },
    }


@mock.patch("exodus_lambda.functions.origin_request.cachetools")
def test_origin_request_listing_typical(mocked_cache, caplog):
    req_uri = "/content/dist/rhel/server/7/listing"

    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}
    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

    assert "Handling listing request: %s" % req_uri in caplog.text
    # It should successfully generate appropriate listing response.
    assert request == {
        "body": "7.0\n7.1\n7.2\n7.3\n7.4\n7.5\n7.6\n7.7\n7.8\n7.9\n7Server\n",
        "status": "200",
        "statusDescription": "OK",
        "headers": {
            "content-type": [{"key": "Content-Type", "value": "text/plain"}]
        },
    }


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_listing_not_found(
    mocked_datetime, mocked_cache, mocked_boto3_client, caplog
):
    req_uri = "/some/invalid/uri/listing"

    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}
    mocked_boto3_client().query.return_value = {"Items": []}

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}
    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

    assert "Handling listing request: %s" % req_uri in caplog.text
    # It should fail to generate listing.
    assert "No listing found for '/some/invalid/uri/listing'" in caplog.text
    # It should fail to find file-object.
    assert "No item found for '%s'", req_uri in caplog.text
    # It should return 404.
    assert request == {"status": "404", "statusDescription": "Not Found"}


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_listing_data_not_found(
    mocked_datetime, mocked_cache, mocked_boto3_client, caplog
):
    req_uri = "/content/dist/rhel/server/7/listing"

    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": {}}
    mocked_boto3_client().query.return_value = {"Items": []}

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}
    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

    assert "Handling listing request: %s" % req_uri in caplog.text
    # It should fail to find listing data.
    assert "No listing data defined" in caplog.text
    # It should fail to find file-object.
    assert "No item found for '%s'", req_uri in caplog.text
    # It should return 404.
    assert request == {"status": "404", "statusDescription": "Not Found"}
