import json
import logging

import mock
import pytest

from exodus_lambda.functions.origin_response import OriginResponse

from ..test_utils.utils import generate_test_config

TEST_CONF = generate_test_config()
MAX_AGE = TEST_CONF["headers"]["max_age"]


@pytest.mark.parametrize(
    "original_uri, want_repr_digest, x_exodus_query",
    [
        ("/some/repo/listing", True, False),
        ("/some/repo/repodata/repomd.xml", True, False),
        ("/some/repo/ostree/repo/refs/heads/ok/test", False, True),
    ],
)
def test_origin_response_valid_headers(
    original_uri, want_repr_digest, x_exodus_query
):
    event = {
        "Records": [
            {
                "cf": {
                    "request": {
                        "uri": "/be7f3007df3e51fb48fff57da9c01c52e6b8e60eceacab"
                        "7aaf0e05b57578493a",
                        "headers": {
                            "exodus-original-uri": [
                                {
                                    "key": "exodus-original-uri",
                                    "value": original_uri,
                                }
                            ]
                        },
                    },
                    "response": {"headers": {}},
                }
            }
        ]
    }

    expected_headers = {
        "cache-control": [
            {"key": "Cache-Control", "value": f"max-age={MAX_AGE}"}
        ]
    }

    if want_repr_digest:
        event["Records"][0]["cf"]["request"]["headers"]["want-repr-digest"] = [
            {"key": "Want-Repr-Digest", "value": "sha-256"}
        ]
        expected_headers["repr-digest"] = [
            {
                "key": "Repr-Digest",
                "value": "sha-256=:vn8wB98+UftI//V9qcAcUua45g7OrKt6rw4FtXV4STo=:",
            }
        ]

    if x_exodus_query:
        event["Records"][0]["cf"]["request"]["headers"]["x-exodus-query"] = [
            {"key": "X-Exodus-Query", "value": "true"}
        ]
        expected_headers["x-exodus-version"] = [
            {
                "key": "X-Exodus-Version",
                "value": "fake version",
            }
        ]

    response = OriginResponse(conf_file=TEST_CONF).handler(event, context=None)
    assert response["headers"] == expected_headers


def test_origin_response_empty_headers():
    event = {
        "Records": [
            {"cf": {"request": {"headers": {}}, "response": {"headers": {}}}}
        ]
    }

    response = OriginResponse(conf_file=TEST_CONF).handler(event, context=None)
    assert response["headers"] == {}


def test_origin_response_missing_headers():
    event = {"Records": [{"cf": {"request": {}, "response": {}}}]}

    response = OriginResponse(conf_file=TEST_CONF).handler(event, context=None)
    assert response == {}


def test_origin_response_logger(caplog):
    event = {
        "Records": [
            {
                "cf": {
                    "request": {
                        "uri": "/be7f3007df3e51fb48fff57da9c01c52e6b8e60eceacab"
                        "7aaf0e05b57578493a",
                        "headers": {
                            "exodus-original-uri": [
                                {
                                    "key": "exodus-original-uri",
                                    "value": "/some/repo/repodata/repomd.xml",
                                }
                            ]
                        },
                    },
                    "response": {"headers": {}},
                }
            }
        ]
    }

    with caplog.at_level(logging.DEBUG):
        OriginResponse(conf_file=TEST_CONF).handler(event, context=None)

    dict_log = {}
    for count, item in enumerate(caplog.text.splitlines()):
        dict_log[count] = json.loads(item)

    assert dict_log[0] == {
        "level": "DEBUG",
        "time": mock.ANY,
        "aws-request-id": None,
        "message": "Incoming event for origin_response",
        "request": {
            "headers": {
                "exodus-original-uri": [
                    {
                        "key": "exodus-original-uri",
                        "value": "/some/repo/repodata/repomd.xml",
                    }
                ]
            },
            "uri": "/be7f3007df3e51fb48fff57da9c01c52e6b8e60eceacab7aaf0e05b57578493a",
        },
        "response": {"headers": {}},
    }
    assert dict_log[1] == {
        "level": "DEBUG",
        "time": mock.ANY,
        "aws-request-id": None,
        "message": "Completed response processing",
        "request": {
            "headers": {
                "exodus-original-uri": [
                    {
                        "key": "exodus-original-uri",
                        "value": "/some/repo/repodata/repomd.xml",
                    }
                ]
            },
            "uri": "/be7f3007df3e51fb48fff57da9c01c52e6b8e60eceacab7aaf0e05b57578493a",
        },
        "response": {
            "headers": {
                "cache-control": [
                    {"key": "Cache-Control", "value": "max-age=600"}
                ]
            }
        },
    }
