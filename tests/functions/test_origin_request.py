import copy
import gzip
import json
import logging
from urllib.parse import unquote, urlencode

import mock
import pytest

from exodus_lambda.functions.origin_request import OriginRequest

from ..test_utils.utils import generate_test_config, mock_definitions

TEST_PATH = "/origin/rpms/repo/ver/dir/filename.ext"
MOCKED_DT = "2020-02-17T15:38:05.864+00:00"
TEST_CONF = generate_test_config()


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
        (
            # encoded URI should be decoded
            "/content/dist/rhel/rhui/server/7/7Server/some%5Efile",
            "/content/dist/rhel/server/7/7.9/some^file",
            "text/plain",
        ),
        (
            # but it is also OK to not encode that character
            "/content/dist/rhel/rhui/server/7/7Server/some^file",
            "/content/dist/rhel/server/7/7.9/some^file",
            "text/plain",
        ),
        (
            # this tricky case is trying to ensure that, even for "special"
            # paths like /listing, if the client encodes parts of the URI it
            # still all works normally.
            "/content/dist/rhel/rhui/server/7/li%73ting",
            "/content/dist/rhel/rhui/server/7/listing",
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
        "encoded URI",
        "reserved char no encoding",
        "encoded listing",
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

    assert "Incoming request value for origin_request" in caplog.text

    req_uri_decoded = unquote(req_uri)

    if req_uri_decoded.endswith("/listing"):
        assert "Handling listing request" in caplog.text
        assert "Generated listing request response" in caplog.text
        assert request["body"]
    else:
        assert f"Item found for URI: {real_uri}" in caplog.text
        assert request == {
            "uri": "/e4a3f2sum",
            "querystring": urlencode({"response-content-type": content_type}),
            "headers": {
                "exodus-original-uri": [
                    {"key": "exodus-original-uri", "value": req_uri_decoded}
                ]
            },
        }


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
def test_origin_request_db_failover(
    mocked_cache,
    mocked_boto3_client,
    caplog,
):
    """Table queries can failover to secondary regions on error."""
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}

    # Simulate dynamodb raising errors in some regions.
    bad_client1 = mock.Mock(spec=["query"])
    bad_client1.query.side_effect = RuntimeError("simulated error 1")
    bad_client2 = mock.Mock(spec=["query"])
    bad_client2.query.side_effect = RuntimeError("simulated error 2")
    good_client = mock.Mock(spec=["query"])
    good_client.query.return_value = {
        "Items": [
            {
                "web_uri": {"S": "/some/uri"},
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                "object_key": {"S": "e4a3f2sum"},
                "content_type": {"S": "text/plain"},
            }
        ]
    }

    # Make it so that the first two constructed clients (i.e. first two regions)
    # raise an error and the third will succeed
    mocked_boto3_client.side_effect = [
        bad_client1,
        bad_client2,
        good_client,
    ]

    event = {
        "Records": [{"cf": {"request": {"uri": "/some/uri", "headers": {}}}}]
    }

    request = OriginRequest(
        conf_file=TEST_CONF,
    ).handler(event, context=None)

    # It should ultimately succeed and rewrite the request to use
    # object key as normal
    assert request["uri"] == "/e4a3f2sum"

    # But logs should mention that errors and failover occurred
    assert (
        "Error querying table test-table in region us-east-1"
        in caplog.messages
    )
    assert (
        "Error querying table test-table in region us-east-2"
        in caplog.messages
    )
    assert (
        "Failover: query for table test-table succeeded in region us-west-1 after prior errors"
        in caplog.messages
    )

    # With exception details logged also
    assert "simulated error 1" in caplog.text
    assert "simulated error 2" in caplog.text


def test_origin_request_fail_uri_validation(caplog):
    # Validation fails for too lengthy URIs.
    event = {
        "Records": [
            {"cf": {"request": {"uri": "o" * 2001, "querystring": ""}}}
        ]
    }

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(conf_file=TEST_CONF).handler(
            event, context=None
        )

    # It should return 400 status code.
    assert request == {"status": "400", "statusDescription": "Bad Request"}
    # Log should only contain URI error message (and the init logger message).
    assert [json.loads(log) for log in caplog.text.splitlines()] == [
        {
            "level": "INFO",
            "time": mock.ANY,
            "aws-request-id": None,
            "message": "Initializing logger...",
            "logger": "origin-request",
            "request": None,
            "response": None,
        },
        {
            "level": "ERROR",
            "time": mock.ANY,
            "aws-request-id": None,
            "message": f"uri exceeds length limits: {('o' * 2001)}",
            "logger": "origin-request",
            "request": None,
            "response": None,
        },
    ]


def test_origin_request_fail_querystring_validation(caplog):
    # Validation fails for too lengthy URIs.
    event = {
        "Records": [
            {"cf": {"request": {"uri": "/", "querystring": "o" * 4001}}}
        ]
    }

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(conf_file=TEST_CONF).handler(
            event, context=None
        )

    # It should return 400 status code.
    assert request == {"status": "400", "statusDescription": "Bad Request"}
    # Log should only contain querystring error message (and the init logger message).
    assert [json.loads(log) for log in caplog.text.splitlines()] == [
        {
            "level": "INFO",
            "time": mock.ANY,
            "aws-request-id": None,
            "message": "Initializing logger...",
            "logger": "origin-request",
            "request": None,
            "response": None,
        },
        {
            "level": "ERROR",
            "time": mock.ANY,
            "aws-request-id": None,
            "message": f"querystring exceeds length limits: {('o' * 4001)}",
            "logger": "origin-request",
            "request": None,
            "response": None,
        },
    ]


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
    assert f"No item found for URI: {TEST_PATH}" in caplog.text


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
        f"Exception occurred while processing item: {mocked_boto3_client().query()['Items'][0]}"
        in caplog.text
    )


@pytest.mark.parametrize("binary_config", (True, False))
@mock.patch("boto3.client")
def test_origin_request_definitions(mocked_boto3_client, binary_config: bool):
    mocked_defs = mock_definitions()
    json_defs = json.dumps(mocked_defs)
    config: dict[str, str | bytes] = {}

    if binary_config:
        # Config in the style exodus-gw writes from late 2024 onwards
        config["B"] = gzip.compress(json_defs.encode())
    else:
        # Older-style config
        config["S"] = json_defs

    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                "config_id": {"S": "exodus-config"},
                "config": config,
            }
        ]
    }

    assert OriginRequest(conf_file=TEST_CONF).definitions == mocked_defs


@mock.patch("boto3.client")
def test_origin_request_definitions_not_found(mocked_boto3_client):
    expected_defs = {
        "origin_alias": [],
        "rhui_alias": [],
        "releasever_alias": [],
        "listing": {},
    }
    mocked_boto3_client().query.return_value = {"Items": []}

    assert OriginRequest(conf_file=TEST_CONF).definitions == expected_defs


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

    assert f"Item found for URI: {real_uri}" in caplog.text

    assert request == {
        "uri": "/e4a3f2sum",
        "querystring": urlencode(
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

    assert f"Handling listing request: {req_uri}" in caplog.text
    # It should successfully generate appropriate listing response.
    assert request == {
        "body": "7.0\n7.1\n7.2\n7.3\n7.4\n7.5\n7.6\n7.7\n7.8\n7.9\n7Server\n",
        "status": "200",
        "statusDescription": "OK",
        "headers": {
            "content-type": [{"key": "Content-Type", "value": "text/plain"}],
            "cache-control": [
                {"key": "Cache-Control", "value": "max-age=600"}
            ],
        },
    }


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
def test_origin_request_listing_fallback(
    mocked_cache, mocked_boto3_client, caplog
):

    req_uri = "/content/dist/rhel/myOwnRHEL/listing"
    real_uri = "/content/dist/rhel/extraSpecialRHEL/listing"
    definitions = mock_definitions()
    definitions["listing"]["/content/dist/rhel/extraSpecialRHEL"] = {
        "var": "basearch",
        "values": ["x86_64"],
    }
    test_alias = {
        "src": "/content/dist/rhel/myOwnRHEL",
        "dest": "/content/dist/rhel/extraSpecialRHEL",
        "exclude_paths": ["listing"],
    }
    definitions["releasever_alias"].append(test_alias)
    mocked_cache.TTLCache.return_value = {"exodus-config": definitions}

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}

    # No file in DB for handle_file_request to find.
    mocked_boto3_client().query.side_effect = [
        {"Items": []},  # req_uri
        {"Items": []},  # req_uri index page
    ]

    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

    assert f"Handling listing request: {req_uri}" in caplog.text
    assert f"No item found for URI: {req_uri}" in caplog.text
    assert f"Handling listing request: {real_uri}" in caplog.text
    # It should successfully generate appropriate listing response.
    assert request == {
        "body": "x86_64\n",
        "status": "200",
        "statusDescription": "OK",
        "headers": {
            "content-type": [{"key": "Content-Type", "value": "text/plain"}],
            "cache-control": [
                {"key": "Cache-Control", "value": "max-age=600"}
            ],
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

    assert f"Handling listing request: {req_uri}" in caplog.text
    # It should fail to generate listing.
    assert "No listing found for URI: /some/invalid/uri/listing" in caplog.text
    # It should fail to find file-object.
    assert f"No item found for URI: {req_uri}" in caplog.text
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

    assert f"Handling listing request: {req_uri}" in caplog.text
    # It should fail to find listing data.
    assert "No listing data defined" in caplog.text
    # It should fail to find file-object.
    assert f"No item found for URI: {req_uri}" in caplog.text
    # It should return 404.
    assert request == {"status": "404", "statusDescription": "Not Found"}


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_absent_items(
    mocked_datetime,
    mocked_cache,
    mocked_boto3_client,
    caplog,
):
    req_uri = "/content/dist/rhel/some/deletion.iso"
    real_uri = "/content/dist/rhel/some/deletion.iso"
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "web_uri": {"S": real_uri},
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                "object_key": {"S": "absent"},
            }
        ]
    }

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(
            conf_file=TEST_CONF,
        ).handler(event, context=None)

    assert f"Item absent for URI: {real_uri}" in caplog.text

    assert request == {"status": "404", "statusDescription": "Not Found"}


@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_cookie_uri(mocked_datetime, caplog):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT

    uri = "/_/cookie/origin/repo/ver/dir/filename.ext"
    event = {
        "Records": [
            {
                "cf": {
                    "request": {
                        "uri": uri,
                        "headers": {},
                        "querystring": (
                            "Expires=1644971400&"
                            "Signature=DxQExeKUk0OJ~qafWOIow1OM8Nil9x4JBjpgtODY1AoIuH-FcW4nt~AcAQmJ1WHRqYIuC79INWk9RTyOokj-Ao6e6i5r6AcPKvhTTyOgRkg9Ywfzf~fUdBENi3k9q4sWgbvND5kiZRZwj3DBc4s0bX82rYYuuSGnjNyjshYhlVU_&"
                            "CloudFront-Cookies=WyJDbG91ZEZyb250LUtleS1QYWlyLUlkPVhYWFhYWFhYWFhYWFhYOyBTZWN1cmU7IEh0dHBPbmx5OyBTYW1lU2l0ZT1sYXg7IERvbWFpbj1sb2NhbGhvc3Q6ODA0OTsgUGF0aD0vY29udGVudC87IE1heC1BZ2U9NDMyMDAiLCAiQ2xvdWRGcm9udC1Qb2xpY3k9ZXlKVGRHRjBaVzFsYm5RaU9sdDdJbEpsYzI5MWNtTmxJam9pYUhSMGNEb3ZMMnh2WTJGc2FHOXpkRG80TURRNUwyTnZiblJsYm5RdktpSXNJa052Ym1ScGRHbHZiaUk2ZXlKRVlYUmxUR1Z6YzFSb1lXNGlPbnNpUVZkVE9rVndiMk5vVkdsdFpTSTZNVFkwTlRBeE1qZ3dNSDE5ZlYxOTsgU2VjdXJlOyBIdHRwT25seTsgU2FtZVNpdGU9bGF4OyBEb21haW49bG9jYWxob3N0OjgwNDk7IFBhdGg9L2NvbnRlbnQvOyBNYXgtQWdlPTQzMjAwIiwgIkNsb3VkRnJvbnQtU2lnbmF0dXJlPU5XUGZnb3REdTJEa0g0ZjRkNjhlVWtMTk5hVmZKR2hpenp4UlJleGI1NVh0Y0o3Qzk2cEF4ekd3cX56UWJoNndyMHhhMlh4Zll3UjV5dEs1MmJXQ3JCTGJWVHI5WWd0M2Z3Z3FDZTl1cWl1dnJoU3V-WDd3Z0VPbkVvT053Sng2WGw1VkFERU4yYXBVblBMQ1hJVEQybXYtNnJDaFhmemdaMXg0UER5OGo4MF87IFNlY3VyZTsgSHR0cE9ubHk7IFNhbWVTaXRlPWxheDsgRG9tYWluPWxvY2FsaG9zdDo4MDQ5OyBQYXRoPS9jb250ZW50LzsgTWF4LUFnZT00MzIwMCIsICJDbG91ZEZyb250LUtleS1QYWlyLUlkPVhYWFhYWFhYWFhYWFhYOyBTZWN1cmU7IEh0dHBPbmx5OyBTYW1lU2l0ZT1sYXg7IERvbWFpbj1sb2NhbGhvc3Q6ODA0OTsgUGF0aD0vb3JpZ2luLzsgTWF4LUFnZT00MzIwMCIsICJDbG91ZEZyb250LVBvbGljeT1leUpUZEdGMFpXMWxiblFpT2x0N0lsSmxjMjkxY21ObElqb2lhSFIwY0RvdkwyeHZZMkZzYUc5emREbzRNRFE1TDI5eWFXZHBiaThxSWl3aVEyOXVaR2wwYVc5dUlqcDdJa1JoZEdWTVpYTnpWR2hoYmlJNmV5SkJWMU02UlhCdlkyaFVhVzFsSWpveE5qUTFNREV5T0RBd2ZYMTlYWDBfOyBTZWN1cmU7IEh0dHBPbmx5OyBTYW1lU2l0ZT1sYXg7IERvbWFpbj1sb2NhbGhvc3Q6ODA0OTsgUGF0aD0vb3JpZ2luLzsgTWF4LUFnZT00MzIwMCIsICJDbG91ZEZyb250LVNpZ25hdHVyZT1NaW8za2w5enpCZXE2WUtjREY0aFdHNGlIRFhnLWRwSnV-VmtkWklYZVhPM0lsZzE3OTZUWlFBZGpLLWN6Tm5aQzBUNWVmVzNEbGlKQWVMSmhYd351MVZoTkpSQ0lvUTZmTGJDVnV4MVRHMzAtUC1FVzR-a1JmU2dlWjV2RVcydTBNWXpsQ0pNZndZSUoxQ1ZlejlMdTJ3a2NIMjFQTkNjc2liS25tTmZjbk1fOyBTZWN1cmU7IEh0dHBPbmx5OyBTYW1lU2l0ZT1sYXg7IERvbWFpbj1sb2NhbGhvc3Q6ODA0OTsgUGF0aD0vb3JpZ2luLzsgTWF4LUFnZT00MzIwMCJd&"
                            "Key-Pair-Id=XXXXXXXXXXXXXX"
                        ),
                    },
                    "config": {
                        "distributionDomainName": "http://localhost:8049"
                    },
                }
            }
        ]
    }

    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

    assert f"Handling cookie request: {uri}" in caplog.text
    assert request["status"] == "302"
    assert request["headers"]["cache-control"] == [{"value": "no-store"}]
    assert request["headers"]["location"] == [
        {"value": "/origin/repo/ver/dir/filename.ext"}
    ]
    assert request["headers"]["set-cookie"] == [
        {
            "value": "CloudFront-Key-Pair-Id=XXXXXXXXXXXXXX; Secure; "
            "HttpOnly; SameSite=lax; Domain=localhost:8049; Path=/content/; "
            "Max-Age=43200"
        },
        {
            "value": "CloudFront-Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaH"
            "R0cDovL2xvY2FsaG9zdDo4MDQ5L2NvbnRlbnQvKiIsIkNvbmRpdGlvbiI6eyJEYXR"
            "lTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTY0NTAxMjgwMH19fV19; "
            "Secure; HttpOnly; SameSite=lax; Domain=localhost:8049; "
            "Path=/content/; Max-Age=43200"
        },
        {
            "value": "CloudFront-Signature=NWPfgotDu2DkH4f4d68eUkLNNaVfJGhizzx"
            "RRexb55XtcJ7C96pAxzGwq~zQbh6wr0xa2XxfYwR5ytK52bWCrBLbVTr9Ygt3fwgq"
            "Ce9uqiuvrhSu~X7wgEOnEoONwJx6Xl5VADEN2apUnPLCXITD2mv-6rChXfzgZ1x4P"
            "Dy8j80_; Secure; HttpOnly; SameSite=lax; Domain=localhost:8049; "
            "Path=/content/; Max-Age=43200"
        },
        {
            "value": "CloudFront-Key-Pair-Id=XXXXXXXXXXXXXX; Secure; "
            "HttpOnly; SameSite=lax; Domain=localhost:8049; Path=/origin/; "
            "Max-Age=43200"
        },
        {
            "value": "CloudFront-Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaH"
            "R0cDovL2xvY2FsaG9zdDo4MDQ5L29yaWdpbi8qIiwiQ29uZGl0aW9uIjp7IkRhdGV"
            "MZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNjQ1MDEyODAwfX19XX0_; "
            "Secure; HttpOnly; SameSite=lax; Domain=localhost:8049; "
            "Path=/origin/; Max-Age=43200"
        },
        {
            "value": "CloudFront-Signature=Mio3kl9zzBeq6YKcDF4hWG4iHDXg-dpJu~V"
            "kdZIXeXO3Ilg1796TZQAdjK-czNnZC0T5efW3DliJAeLJhXw~u1VhNJRCIoQ6fLbC"
            "Vux1TG30-P-EW4~kRfSgeZ5vEW2u0MYzlCJMfwYIJ1CVez9Lu2wkcH21PNCcsibKn"
            "mNfcnM_; Secure; HttpOnly; SameSite=lax; Domain=localhost:8049; "
            "Path=/origin/; Max-Age=43200"
        },
    ]


@pytest.mark.parametrize(
    "cookie_param,error",
    [
        ("", "KeyError"),
        ("CloudFront-Cookies=WyJDbG91ZEZyb250LUtleSs&", "binascii.Error"),
        (
            "CloudFront-Cookies=eyJ0ZXN0aW5nIjogWzEsMiwzXQ==&",
            "JSONDecodeError",
        ),
        (
            "CloudFront-Cookies=IkNsb3VkRnJvbnQtS2V5LVBhaXItSWQ9WFhYWFhYWFhYWFhYWFg7IFNlY3VyZTsgSHR0cE9ubHk7IFNhbWXaXRnWxheAaG9zdDo4MDQ5OyBQYXRoPS9jb250ZW50LzsgTWF4LUFnZT00MzIwMCI=&",
            "UnicodeDecodeError",
        ),
    ],
    ids=["absent", "binascii", "json", "unicode"],
)
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_invalid_cookie(
    mocked_datetime, cookie_param, error, caplog
):
    caplog.set_level(logging.DEBUG, "exodus-lambda")
    mocked_datetime.now().isoformat.return_value = MOCKED_DT

    uri = "/_/cookie/origin/repo/ver/dir/filename.ext"
    event = {
        "Records": [
            {
                "cf": {
                    "request": {
                        "uri": uri,
                        "headers": {},
                        "querystring": (
                            f"{cookie_param}"
                            "Expires=1644971400&"
                            "Signature=DxQExeKUk0OJ~qafWOIow1OM8Nil9x4JBjpgtODY1AoIuH-FcW4nt~AcAQmJ1WHRqYIuC79INWk9RTyOokj-Ao6e6i5r6AcPKvhTTyOgRkg9Ywfzf~fUdBENi3k9q4sWgbvND5kiZRZwj3DBc4s0bX82rYYuuSGnjNyjshYhlVU_&"
                            "Key-Pair-Id=XXXXXXXXXXXXXX"
                        ),
                    },
                    "config": {
                        "distributionDomainName": "http://localhost:8049"
                    },
                }
            }
        ]
    }

    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

    assert request == {"status": "400", "statusDescription": "Bad Request"}
    assert "Unable to load cookies from redirect request" in caplog.text
    assert error in caplog.text


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_with_version_check(
    mocked_datetime, mocked_cache, mocked_boto3_client, caplog
):
    req_uri = "/content/dist/rhel/server/7/listing"

    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": {}}
    mocked_boto3_client().query.return_value = {"Items": []}

    event = {
        "Records": [
            {
                "cf": {
                    "request": {
                        "uri": req_uri,
                        "headers": {"x-exodus-query": 1},
                    }
                }
            }
        ]
    }
    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)
    assert request == {
        "status": "404",
        "statusDescription": "Not Found",
        "headers": {
            "x-exodus-version": [
                {"key": "X-Exodus-Version", "value": "fake version"}
            ]
        },
    }


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_directly_request_autoindex_uri(
    mocked_datetime, mocked_cache, mocked_boto3_client, caplog
):
    req_uri = "/content/dist/rhel/repo/x86_64/Packages/.__exodus_autoindex"

    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": {}}
    mocked_boto3_client().query.return_value = {
        "Items": [
            {
                "web_uri": {"S": req_uri},
                "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                "object_key": {"S": "e4a3f2b1sum"},
            },
        ]
    }

    event = {
        "Records": [
            {
                "cf": {
                    "request": {
                        "uri": req_uri,
                    }
                }
            }
        ]
    }
    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)
    assert request == {
        "status": "404",
        "statusDescription": "Not Found",
    }


@pytest.mark.parametrize(
    "req_uri, index_uri, expected_redirect",
    [
        (
            "/content/dist/rhel/repo/x86_64/Packages/",
            "/content/dist/rhel/repo/x86_64/Packages/.__exodus_autoindex",
            None,
        ),
        (
            "/content/dist/rhel/repo/x86_64/Packages",
            "/content/dist/rhel/repo/x86_64/Packages/.__exodus_autoindex",
            "/content/dist/rhel/repo/x86_64/Packages/",
        ),
        (
            # Case where an alias is involved.
            # The user requests a path on the src side of a /rhui/ alias:
            "/content/dist/rhel8/rhui/repo/x86_64/Packages",
            # The actual index object is stored on the dest side:
            "/content/dist/rhel8/repo/x86_64/Packages/.__exodus_autoindex",
            # The redirect works but retains the src side:
            "/content/dist/rhel8/rhui/repo/x86_64/Packages/",
        ),
    ],
)
@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_autoindex(
    mocked_datetime,
    mocked_cache,
    mocked_boto3_client,
    req_uri,
    index_uri,
    expected_redirect,
    caplog,
):
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}

    mock_query = mocked_boto3_client().query

    # The query function is expected to be called twice:
    mock_query.side_effect = [
        # First it's called with the original requested URI,
        # which should find nothing
        {"Items": []},
        # Then it's called with the autoindex URI, which should return a valid item
        {
            "Items": [
                {
                    "web_uri": {"S": index_uri},
                    "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                    "object_key": {"S": "e4a3f2b1sum"},
                },
            ]
        },
    ]

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}

    with caplog.at_level(logging.DEBUG):
        response = OriginRequest(
            conf_file=TEST_CONF,
        ).handler(event, context=None)

    assert f"Item found for URI: {index_uri}" in caplog.text

    if expected_redirect:
        # We found an index but we're expecting a redirect to another URI.
        expected_response = {
            "headers": {"location": [{"value": expected_redirect}]},
            "status": "302",
        }
    else:
        # We found an index and we're serving it normally.
        expected_response = {
            "uri": "/e4a3f2b1sum",
            "querystring": urlencode(
                {"response-content-type": "application/octet-stream"}
            ),
            "headers": {
                "exodus-original-uri": [
                    {"key": "exodus-original-uri", "value": req_uri}
                ]
            },
        }

    assert response == expected_response


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_fallback_uri(
    mocked_datetime,
    mocked_cache,
    mocked_boto3_client,
    caplog,
):
    # After the introduction of exclusion_paths, some files are still stored
    # under the aliased uri. We try the "correct" uri and fallback to the older aliased uri

    req_uri = "/content/dist/rhel8/8/files/deletion.iso"
    real_uri = "/content/dist/rhel8/8.5/files/deletion.iso"
    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}

    mocked_boto3_client().query.side_effect = [
        {"Items": []},  # req_uri
        {"Items": []},  # req_uri index page
        {
            "Items": [
                {
                    "web_uri": {"S": real_uri},
                    "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                    "object_key": {"S": "e4a3f2sum"},
                }
            ]
        },
    ]
    expected_boto_calls = [
        mock.call(
            TableName="test-table",
            Limit=1,
            ConsistentRead=True,
            ScanIndexForward=False,
            KeyConditionExpression="web_uri = :u and from_date <= :d",
            ExpressionAttributeValues={
                ":u": {"S": uri},
                ":d": {"S": "2020-02-17T15:38:05.864+00:00"},
            },
        )
        for uri in [
            "/content/dist/rhel8/8/files/deletion.iso",
            "/content/dist/rhel8/8/files/deletion.iso/.__exodus_autoindex",
            "/content/dist/rhel8/8.5/files/deletion.iso",
        ]
    ]
    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(
            conf_file=TEST_CONF,
        ).handler(event, context=None)

    assert f"Item found for URI: {real_uri}" in caplog.text
    assert f"No item found for URI: {req_uri}"

    mocked_boto3_client().query.assert_has_calls(expected_boto_calls)
    assert request == {
        "uri": "/e4a3f2sum",
        "querystring": urlencode(
            {"response-content-type": "application/octet-stream"}
        ),
        "headers": {
            "exodus-original-uri": [
                {"key": "exodus-original-uri", "value": req_uri}
            ]
        },
    }


@pytest.mark.parametrize(
    "content_exists, mirror_reads",
    [
        (
            False,
            1,
        ),
        (True, 1),
        (
            False,
            0,
        ),
        (True, 0),
    ],
    ids=[
        "mirrored reads enabled, content exists",
        "mirrored reads enabled, content does not exist",
        "mirrored reads disabled, content exists",
        "mirrored reads disabled, content does not exist",
    ],
)
@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_mirrored_reads_dest_alias(
    mocked_datetime,
    mocked_cache,
    mocked_boto3_client,
    content_exists,
    mirror_reads,
    caplog,
):
    """Given the releasever alias /content/dist/rhel9/9 => /content/dist/rhel9/9.0,
    if the client requests /content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-primary.xml.gz,
    exodus-cdn should only lookup that path. Although a /content/dist/rhel9/9 => /content/dist/rhel9/9.0
    alias exists, no mirroring occurs because this incoming request already uses the destination side of
    the alias. This behavior is expected regardless if mirrored writes are enabled or disabled.
    """
    conf = copy.deepcopy(TEST_CONF)
    conf["mirror_reads"] = mirror_reads

    # A path which involves the dest side of the releasever alias
    req_uri = "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-primary.xml.gz,"

    # The expected queries differ based on whether we expect to find content at the the resolved
    # alias.
    if content_exists:
        mocked_boto3_client().query.side_effect = [
            {
                "Items": [
                    {
                        "web_uri": {"S": req_uri},
                        "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                        "object_key": {"S": "e4a3f2sum"},
                    }
                ]
            },
        ]
        expected_queried_uris = [req_uri]
    else:
        mocked_boto3_client().query.side_effect = [
            {"Items": []},  # req_uri
            {"Items": []},  # req_uri autoindex
        ]
        expected_queried_uris = [
            req_uri,
            f"{req_uri}/.__exodus_autoindex",
        ]

    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(
            conf_file=conf,
        ).handler(event, context=None)

    assert "Incoming request value for origin_request" in caplog.text

    req_uri_decoded = unquote(req_uri)

    if content_exists:
        assert f"Item found for URI: {req_uri}" in caplog.text
        assert request == {
            "uri": "/e4a3f2sum",
            "headers": {
                "exodus-original-uri": [
                    {"key": "exodus-original-uri", "value": req_uri_decoded}
                ]
            },
            "querystring": urlencode(
                {"response-content-type": "application/octet-stream"}
            ),
        }
    else:
        for uri in expected_queried_uris:
            if not uri.endswith(".__exodus_autoindex"):
                assert f"No item found for URI: {uri}" in caplog.text
        assert request == {
            "status": "404",
            "statusDescription": "Not Found",
        }

    expected_boto_calls = [
        mock.call(
            TableName="test-table",
            Limit=1,
            ConsistentRead=True,
            ScanIndexForward=False,
            KeyConditionExpression="web_uri = :u and from_date <= :d",
            ExpressionAttributeValues={
                ":u": {"S": uri},
                ":d": {"S": "2020-02-17T15:38:05.864+00:00"},
            },
        )
        for uri in expected_queried_uris
    ]
    mocked_boto3_client().query.assert_has_calls(expected_boto_calls)


@pytest.mark.parametrize(
    "boto_side_effect, expected_queried_uris, found_uri, mirror_reads",
    [
        (
            [
                {"Items": []},  # resolved alias
                {"Items": []},  # autoindex
                {
                    "Items": [
                        {
                            "web_uri": {
                                "S": "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml"
                            },
                            "from_date": {
                                "S": "2020-02-17T00:00:00.000+00:00"
                            },
                            "object_key": {"S": "e4a3f2sum"},
                        }
                    ]
                },
            ],
            [
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml/.__exodus_autoindex",
                "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml",
            ],
            "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml",
            "true",
        ),
        (
            [
                {
                    "Items": [
                        {
                            "web_uri": {
                                "S": "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml"
                            },
                            "from_date": {
                                "S": "2020-02-17T00:00:00.000+00:00"
                            },
                            "object_key": {"S": "e4a3f2sum"},
                        }
                    ]
                },
            ],
            [
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
            ],
            "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
            "true",
        ),
        (
            [
                {"Items": []},  # resolved alias
                {"Items": []},  # resolved alias autoindex
                {"Items": []},  # original uri
                {"Items": []},  # original uri autoindex
            ],
            [
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml/.__exodus_autoindex",
                "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml",
                "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml/.__exodus_autoindex",
            ],
            "",
            "true",
        ),
        (
            [
                {
                    "Items": [
                        {
                            "web_uri": {
                                "S": "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml"
                            },
                            "from_date": {
                                "S": "2020-02-17T00:00:00.000+00:00"
                            },
                            "object_key": {"S": "e4a3f2sum"},
                        }
                    ]
                },
            ],
            [
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
            ],
            "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
            "false",
        ),
        (
            [
                {"Items": []},  # resolved alias
                {"Items": []},  # resolved alias autoindex
            ],
            [
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml/.__exodus_autoindex",
            ],
            "",
            "false",
        ),
    ],
    ids=[
        "mirrored reads enabled, content at resolved alias does not exist, but content at original uri exists",
        "mirrored reads enabled, content at resolved alias exists",
        "mirrored reads enabled, neither content at resolved alias nor original uri exists",
        "mirrored reads disabled, content at resolved alias exists",
        "mirrored reads disabled, content at resolved alias does not exist",
    ],
)
@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_mirrored_reads_enabled_src_alias(
    mocked_datetime,
    mocked_cache,
    mocked_boto3_client,
    boto_side_effect,
    expected_queried_uris,
    found_uri,
    mirror_reads,
    caplog,
):
    """Given the releasever alias /content/dist/rhel9/9 => /content/dist/rhel9/9.0,
    if the client requests /content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml,
    exodus-cdn should first lookup content for the path with the alias resolved
    (/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml), and only if that lookup
    finds no item, exodus-cdn looks up content for the path with the alias not resolved,
    /content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml.

    When mirrored reads are disabled, exodus-cdn only performs the first lookup (i.e.,
    exodus-cdn will only look up content for the path with the alias resolved,
    /content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml)."""
    # The requested uri, which involves the src side of a releasever alias
    req_uri = (
        "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml"
    )

    conf = copy.deepcopy(TEST_CONF)
    conf["mirror_reads"] = mirror_reads

    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}
    mocked_boto3_client().query.side_effect = boto_side_effect

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(
            conf_file=conf,
        ).handler(event, context=None)

    assert "Incoming request value for origin_request" in caplog.text

    req_uri_decoded = unquote(req_uri)

    if found_uri:
        assert f"Item found for URI: {found_uri}" in caplog.text
        assert request == {
            "uri": "/e4a3f2sum",
            "headers": {
                "exodus-original-uri": [
                    {"key": "exodus-original-uri", "value": req_uri_decoded}
                ]
            },
            "querystring": urlencode(
                {"response-content-type": "application/octet-stream"}
            ),
        }
    else:
        for uri in expected_queried_uris:
            if not uri.endswith(".__exodus_autoindex"):
                assert f"No item found for URI: {uri}" in caplog.text
        assert request == {
            "status": "404",
            "statusDescription": "Not Found",
        }

    expected_boto_calls = [
        mock.call(
            TableName="test-table",
            Limit=1,
            ConsistentRead=True,
            ScanIndexForward=False,
            KeyConditionExpression="web_uri = :u and from_date <= :d",
            ExpressionAttributeValues={
                ":u": {"S": uri},
                ":d": {"S": "2020-02-17T15:38:05.864+00:00"},
            },
        )
        for uri in expected_queried_uris
    ]
    mocked_boto3_client().query.assert_has_calls(expected_boto_calls)


@pytest.mark.parametrize(
    "boto_side_effect, expected_queried_uris, found_uri, mirror_reads",
    [
        (
            [
                {"Items": []},  # resolved alias
                {"Items": []},  # autoindex
                {
                    "Items": [
                        {
                            "web_uri": {
                                "S": "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml"
                            },
                            "from_date": {
                                "S": "2020-02-17T00:00:00.000+00:00"
                            },
                            "object_key": {"S": "e4a3f2sum"},
                        }
                    ]
                },
            ],
            [
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml/.__exodus_autoindex",
                "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml",
            ],
            "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml",
            "true",
        ),
        (
            [
                {
                    "Items": [
                        {
                            "web_uri": {
                                "S": "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml"
                            },
                            "from_date": {
                                "S": "2020-02-17T00:00:00.000+00:00"
                            },
                            "object_key": {"S": "e4a3f2sum"},
                        }
                    ]
                },
            ],
            [
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
            ],
            "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
            "true",
        ),
        (
            [
                {"Items": []},  # resolved alias
                {"Items": []},  # autoindex
                {"Items": []},  # original uri
                {"Items": []},  # original uri autoindex
            ],
            [
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml/.__exodus_autoindex",
                "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml",
                "/content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml/.__exodus_autoindex",
            ],
            "",
            "true",
        ),
        (
            [
                {
                    "Items": [
                        {
                            "web_uri": {
                                "S": "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml"
                            },
                            "from_date": {
                                "S": "2020-02-17T00:00:00.000+00:00"
                            },
                            "object_key": {"S": "e4a3f2sum"},
                        }
                    ]
                },
            ],
            [
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
            ],
            "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
            "false",
        ),
        (
            [
                {"Items": []},  # resolved alias
                {"Items": []},  # autoindex
            ],
            [
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml",
                "/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml/.__exodus_autoindex",
            ],
            "",
            "false",
        ),
    ],
    ids=[
        "mirrored reads enabled, content exists at original URI but not at resolved alias",
        "mirrored reads enabled, content exists at resolved alias",
        "mirrored reads enabled, no content found at URI",
        "mirrored reads disabled, content exists at resolved alias",
        "mirrored reads disabled, no content found at URI",
    ],
)
@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_mirrored_reads_enabled_rhui_alias(
    mocked_datetime,
    mocked_cache,
    mocked_boto3_client,
    boto_side_effect,
    expected_queried_uris,
    found_uri,
    mirror_reads,
    caplog,
):
    """Given the releasever alias /content/dist/rhel9/9 => /content/dist/rhel9/9.0,
    and the RHUI alias /content/dist/rhel9/rhui => /content/dist/rhel9,
    if the client requests /content/dist/rhel9/rhui/9/x86_64/appstream/os/repodata/abc-comps.xml,
    exodus-cdn should first lookup content for the path with the rhui alias resolved and the releasever
    alias resolved (/content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml); if and only if
    that lookup finds no item, exodus-cdn looks up content for the path with the rhui alias resolved but the
    releasever alias not resolved, /content/dist/rhel9/9/x86_64/appstream/os/repodata/abc-comps.xml.

    When mirrored reads are disabled, exodus-cdn only performs the first lookup (i.e., exodus-cdn
    only looks up content for the path with the rhui and releasever aliases resolved:
    /content/dist/rhel9/9.0/x86_64/appstream/os/repodata/abc-comps.xml).
    """
    # The requested uri, which involves a RHUI and releasever alias
    req_uri = (
        "/content/dist/rhel9/rhui/9/x86_64/appstream/os/repodata/abc-comps.xml"
    )

    conf = copy.deepcopy(TEST_CONF)
    conf["mirror_reads"] = mirror_reads

    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}
    mocked_boto3_client().query.side_effect = boto_side_effect

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(
            conf_file=conf,
        ).handler(event, context=None)

    assert "Incoming request value for origin_request" in caplog.text

    req_uri_decoded = unquote(req_uri)

    if found_uri:
        assert f"Item found for URI: {found_uri}" in caplog.text
        assert request == {
            "uri": "/e4a3f2sum",
            "headers": {
                "exodus-original-uri": [
                    {"key": "exodus-original-uri", "value": req_uri_decoded}
                ]
            },
            "querystring": urlencode(
                {"response-content-type": "application/octet-stream"}
            ),
        }
    else:
        for uri in expected_queried_uris:
            if not uri.endswith(".__exodus_autoindex"):
                assert f"No item found for URI: {uri}" in caplog.text
        assert request == {
            "status": "404",
            "statusDescription": "Not Found",
        }

    expected_boto_calls = [
        mock.call(
            TableName="test-table",
            Limit=1,
            ConsistentRead=True,
            ScanIndexForward=False,
            KeyConditionExpression="web_uri = :u and from_date <= :d",
            ExpressionAttributeValues={
                ":u": {"S": uri},
                ":d": {"S": "2020-02-17T15:38:05.864+00:00"},
            },
        )
        for uri in expected_queried_uris
    ]
    mocked_boto3_client().query.assert_has_calls(expected_boto_calls)


@pytest.mark.parametrize(
    "mirror_reads, content_exists",
    [
        ("True", False),
        ("False", False),
        ("True", True),
        ("False", True),
    ],
    ids=[
        "mirrored reads enabled, content does not exist at URI",
        "mirrored reads disabled, content does not exist at URI",
        "mirrored reads enabled, content exists at URI",
        "mirrored reads disabled, content exists at URI",
    ],
)
@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.cachetools")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_mirrored_reads_no_alias(
    mocked_datetime,
    mocked_cache,
    mocked_boto3_client,
    mirror_reads,
    content_exists,
    caplog,
):
    """If there is not a releasever alias involved, exodus-cdn should only look up the
    requested path (regardless if mirrored writes is enabled or disabled)."""
    conf = copy.deepcopy(TEST_CONF)
    conf["mirror_reads"] = mirror_reads

    # A path which does not involve a releasever alias
    req_uri = "/content/eus/rhel8/8.4/x86_64/baseos/os/repodata/repomd.xml"

    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_cache.TTLCache.return_value = {"exodus-config": mock_definitions()}
    if content_exists:
        mocked_boto3_client().query.side_effect = [
            {
                "Items": [
                    {
                        "web_uri": {"S": req_uri},
                        "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
                        "object_key": {"S": "e4a3f2sum"},
                    }
                ]
            },
        ]
    else:
        mocked_boto3_client().query.side_effect = [
            {"Items": []},  # req_uri
            {"Items": []},  # req_uri autoindex
        ]

    event = {"Records": [{"cf": {"request": {"uri": req_uri, "headers": {}}}}]}

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(
            conf_file=conf,
        ).handler(event, context=None)

    assert "Incoming request value for origin_request" in caplog.text

    if content_exists:
        assert f"Item found for URI: {req_uri}" in caplog.text
        assert request == {
            "uri": "/e4a3f2sum",
            "headers": {
                "exodus-original-uri": [
                    {"key": "exodus-original-uri", "value": req_uri}
                ]
            },
            "querystring": urlencode(
                {"response-content-type": "application/octet-stream"}
            ),
        }
    else:
        assert f"No item found for URI: {req_uri}" in caplog.text
        assert request == {
            "status": "404",
            "statusDescription": "Not Found",
        }

    expected_boto_calls = [
        mock.call(
            TableName="test-table",
            Limit=1,
            ConsistentRead=True,
            ScanIndexForward=False,
            KeyConditionExpression="web_uri = :u and from_date <= :d",
            ExpressionAttributeValues={
                ":u": {"S": req_uri},
                ":d": {"S": "2020-02-17T15:38:05.864+00:00"},
            },
        )
    ]
    mocked_boto3_client().query.assert_has_calls(expected_boto_calls)
