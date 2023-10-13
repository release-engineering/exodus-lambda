import json
import logging
import urllib

import mock
import pytest
from botocore.exceptions import ClientError

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

    assert "Incoming request value for origin_request" in caplog.text

    if req_uri.endswith("/listing"):
        assert "Handling listing request" in caplog.text
        assert "Generated listing request response" in caplog.text
        assert request["body"]
    else:
        assert "Item found for URI: %s" % real_uri in caplog.text
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
    # Log should only contain URI error message.
    assert json.loads(caplog.text) == {
        "level": "ERROR",
        "time": mock.ANY,
        "aws-request-id": None,
        "message": "uri exceeds length limits: %s" % ("o" * 2001),
        "logger": "origin-request",
        "request": None,
        "response": None,
    }


def test_origin_request_fail_querystring_validation(caplog):
    # Validation fails for too lengthy URIs.
    event = {
        "Records": [
            {"cf": {"request": {"uri": "/", "querystring": "o" * 2001}}}
        ]
    }

    with caplog.at_level(logging.DEBUG):
        request = OriginRequest(conf_file=TEST_CONF).handler(
            event, context=None
        )

    # It should return 400 status code.
    assert request == {"status": "400", "statusDescription": "Bad Request"}
    # Log should only contain querystring error message.
    assert json.loads(caplog.text) == {
        "level": "ERROR",
        "time": mock.ANY,
        "aws-request-id": None,
        "message": "querystring exceeds length limits: %s" % ("o" * 2001),
        "logger": "origin-request",
        "request": None,
        "response": None,
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
    assert "No item found for URI: %s" % TEST_PATH in caplog.text


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
        "Exception occurred while processing item: %s"
        % {
            "web_uri": {"S": "/origin/rpms/repo/ver/dir/filename.ext"},
            "from_date": {"S": "2020-02-17T00:00:00.000+00:00"},
        }
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

    assert "Item found for URI: %s" % real_uri in caplog.text

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

    assert "Handling listing request: %s" % req_uri in caplog.text
    # It should fail to generate listing.
    assert "No listing found for URI: /some/invalid/uri/listing" in caplog.text
    # It should fail to find file-object.
    assert "No item found for URI: %s", req_uri in caplog.text
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
    assert "No item found for URI: %s", req_uri in caplog.text
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

    assert "Item absent for URI: %s" % real_uri in caplog.text

    assert request == {"status": "404", "statusDescription": "Not Found"}


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_cookie_uri_content(
    mocked_datetime, mocked_boto3_client, dummy_private_key, caplog
):
    uri = "/_/cookie/content/repo/ver/dir/filename.ext"
    arn = "arn:aws:secretsmanager:example"

    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().get_secret_value.return_value = {
        "ARN": arn,
        "Name": "example_secret",
        "VersionId": "d6acfecc-9c2d-4141-97ad-70b4149424d2",
        "SecretString": json.dumps({"cookie_key": dummy_private_key}),
    }

    event = {
        "Records": [
            {
                "cf": {
                    "request": {"uri": uri, "headers": {}, "querystring": ""},
                    "config": {"distributionDomainName": "ex.cloudfront.net"},
                }
            }
        ]
    }

    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

    assert "Handling cookie request: %s" % uri in caplog.text
    assert request["status"] == "302"
    assert request["headers"]["cache-control"] == [{"value": "no-store"}]
    assert request["headers"]["location"] == [
        {"value": "/content/repo/ver/dir/filename.ext"}
    ]
    assert request["headers"]["set-cookie"] == [
        {
            "value": "CloudFront-Key-Pair-Id=K1MOU91G3N7WPY; Secure; "
            "HttpOnly; SameSite=lax; Domain=ex.cloudfront.net; "
            "Path=/content/; Max-Age=43200"
        },
        {
            "value": "CloudFront-Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaH"
            "R0cHM6Ly9leC5jbG91ZGZyb250Lm5ldC9jb250ZW50LyoiLCJDb25kaXRpb24iOns"
            "iRGF0ZUxlc3NUaGFuIjp7IkFXUzpFcG9jaFRpbWUiOjF9fX1dfQ__; Secure; "
            "HttpOnly; SameSite=lax; Domain=ex.cloudfront.net; "
            "Path=/content/; Max-Age=43200"
        },
        {
            "value": "CloudFront-Signature=G8t5tL4HD1KjlT-qvmw0JIXQESaij7N-Qd-"
            "12DONOWocj9Vo6sFRR1Gxcm4VyxYD2WbsyYPr0DiwkEIVCevp7ET4lakVFrhhpz~l"
            "SR616CqocVzRxOqMiHcoHkQKAhPLU3tbGs1XnSqcl6R6TB4Q1PPvRv2NUHm3T8ujK"
            "1TmKAM_; Secure; HttpOnly; SameSite=lax; Domain=ex.cloudfront.net; "
            "Path=/content/; Max-Age=43200"
        },
    ]


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_cookie_uri_origin(
    mocked_datetime, mocked_boto3_client, dummy_private_key, caplog
):
    uri = "/_/cookie/origin/repo/ver/dir/filename.ext"
    arn = "arn:aws:secretsmanager:example"

    mocked_datetime.now().isoformat.return_value = MOCKED_DT
    mocked_boto3_client().get_secret_value.return_value = {
        "ARN": arn,
        "Name": "example_secret",
        "VersionId": "d6acfecc-9c2d-4141-97ad-70b4149424d2",
        "SecretString": json.dumps({"cookie_key": dummy_private_key}),
    }

    event = {
        "Records": [
            {
                "cf": {
                    "request": {"uri": uri, "headers": {}, "querystring": ""},
                    "config": {"distributionDomainName": "ex.cloudfront.net"},
                }
            }
        ]
    }

    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

    assert "Handling cookie request: %s" % uri in caplog.text
    assert request["status"] == "302"
    assert request["headers"]["cache-control"] == [{"value": "no-store"}]
    assert request["headers"]["location"] == [
        {"value": "/origin/repo/ver/dir/filename.ext"}
    ]
    assert request["headers"]["set-cookie"] == [
        {
            "value": "CloudFront-Key-Pair-Id=K1MOU91G3N7WPY; Secure; "
            "HttpOnly; SameSite=lax; Domain=ex.cloudfront.net; "
            "Path=/origin/; Max-Age=43200"
        },
        {
            "value": "CloudFront-Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaH"
            "R0cHM6Ly9leC5jbG91ZGZyb250Lm5ldC9vcmlnaW4vKiIsIkNvbmRpdGlvbiI6eyJ"
            "EYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MX19fV19; Secure; "
            "HttpOnly; SameSite=lax; Domain=ex.cloudfront.net; "
            "Path=/origin/; Max-Age=43200"
        },
        {
            "value": "CloudFront-Signature=K2Dor2IYm9WViaawbNs-jfsdMuLebxp4LBz"
            "LgnhX8qKZ~NTQYg-x9kIy0DzXCybKJ3bYUomwWJoXWVJxTUjghRBXjBgQtb7GYrk9"
            "yRD6TXJ46uhE9~zSWQInCnwyIAQRgZCuS~BR41C8dPRP56DWSPs0kHWiVGOrP2JI6"
            "YiP3rA_; Secure; HttpOnly; SameSite=lax; Domain=ex.cloudfront.net; "
            "Path=/origin/; Max-Age=43200"
        },
    ]


@mock.patch("boto3.client")
@mock.patch("exodus_lambda.functions.origin_request.datetime")
def test_origin_request_cookie_with_policy_signature(
    mocked_datetime, mocked_boto3_client, caplog
):
    uri = "/_/cookie/origin/repo/ver/dir/filename.ext"
    mocked_datetime.now().isoformat.return_value = MOCKED_DT

    event = {
        "Records": [
            {
                "cf": {
                    "request": {
                        "uri": uri,
                        "headers": {},
                        "querystring": "Policy=policy-from-querystring&Signature=sig-from-querystring",
                    },
                    "config": {"distributionDomainName": "ex.cloudfront.net"},
                }
            }
        ]
    }

    request = OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

    # It shouldn't have looked up the cookie key
    mocked_boto3_client.get_secret_value.assert_not_called()

    assert "Handling cookie request: %s" % uri in caplog.text
    assert request["status"] == "302"
    assert request["headers"]["cache-control"] == [{"value": "no-store"}]
    assert request["headers"]["location"] == [
        {"value": "/origin/repo/ver/dir/filename.ext"}
    ]
    assert request["headers"]["set-cookie"] == [
        {
            "value": "CloudFront-Key-Pair-Id=K1MOU91G3N7WPY; Secure; "
            "HttpOnly; SameSite=lax; Domain=ex.cloudfront.net; "
            "Path=/origin/; Max-Age=43200"
        },
        {
            "value": "CloudFront-Policy=policy-from-querystring; Secure; "
            "HttpOnly; SameSite=lax; Domain=ex.cloudfront.net; "
            "Path=/origin/; Max-Age=43200"
        },
        {
            "value": "CloudFront-Signature=sig-from-querystring; Secure; "
            "HttpOnly; SameSite=lax; Domain=ex.cloudfront.net; "
            "Path=/origin/; Max-Age=43200"
        },
    ]


@mock.patch("boto3.client")
def test_origin_request_cookie_uri_without_secret(mocked_boto3_client, caplog):
    uri = "/_/cookie/origin/repo/ver/dir/filename.ext"
    arn = "arn:aws:secretsmanager:example"

    mocked_boto3_client().get_secret_value.side_effect = ClientError(
        error_response={
            "Code": "ResourceNotFoundException",
            "Message": "Requested resource not found",
        },
        operation_name="get_secret_value",
    )

    event = {
        "Records": [
            {
                "cf": {
                    "request": {
                        "uri": uri,
                        "headers": {},
                        "querystring": "",
                    },
                    "config": {
                        "distributionDomainName": "d149itc2w5r6.cloudfront.net"
                    },
                }
            }
        ]
    }

    with pytest.raises(ClientError):
        OriginRequest(conf_file=TEST_CONF).handler(event, context=None)

    assert "Handling cookie request: %s" % uri in caplog.text
    assert "Couldn't load secret %s" % arn in caplog.text
    assert "botocore.exceptions.ClientError: An error occurred" in caplog.text


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

    assert "Item found for URI: %s" % index_uri in caplog.text

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
            "querystring": urllib.parse.urlencode(
                {"response-content-type": "application/octet-stream"}
            ),
            "headers": {
                "exodus-original-uri": [
                    {"key": "exodus-original-uri", "value": req_uri}
                ]
            },
        }

    assert response == expected_response
