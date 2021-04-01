import json
import logging

import pytest

from exodus_lambda.functions.origin_response import OriginResponse

from ..test_utils.utils import generate_test_config

CONF_PATH = "configuration/lambda_config.json"
TEST_CONF = generate_test_config(CONF_PATH)
MAX_AGE = TEST_CONF["headers"]["max_age"]


@pytest.mark.parametrize(
    "original_uri, want_digest",
    [
        ("/some/repo/listing", True),
        ("/some/repo/repodata/repomd.xml", True),
        ("/some/repo/ostree/repo/refs/heads/ok/test", False),
    ],
)
def test_origin_response_valid_headers(original_uri, want_digest):
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

    if want_digest:
        event["Records"][0]["cf"]["request"]["headers"]["want-digest"] = [
            {"key": "Want-Digest", "value": "sha-256"}
        ]
        expected_headers["digest"] = [
            {
                "key": "Digest",
                "value": "id-sha-256=vn8wB98+UftI//V9qcAcUua45g7OrKt6rw"
                "4FtXV4STo=",
            }
        ]

    response = OriginResponse(conf_file=CONF_PATH).handler(event, context=None)
    assert response["headers"] == expected_headers


@pytest.mark.parametrize(
    "test_input",
    ["/some/repo/some-rpm.rpm", "/some/repo/ostree/repo/refs/heads/nope"],
)
def test_origin_response_empty_headers(test_input):
    event = {
        "Records": [
            {"cf": {"request": {"headers": {}}, "response": {"headers": {}}}}
        ]
    }

    response = OriginResponse(conf_file=CONF_PATH).handler(event, context=None)
    assert response["headers"] == {}


def test_origin_response_missing_headers():
    event = {"Records": [{"cf": {"request": {}, "response": {}}}]}

    response = OriginResponse(conf_file=CONF_PATH).handler(event, context=None)
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
        response = OriginResponse(conf_file=TEST_CONF).handler(
            event, context=None
        )

    assert (
        "Cache-Control header added for '/some/repo/repodata/repomd.xml'"
        in caplog.text
    )
