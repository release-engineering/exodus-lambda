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
