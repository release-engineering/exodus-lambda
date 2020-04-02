import json

import pytest

from exodus_lambda.functions.origin_response import OriginResponse

CONF_PATH = "exodus_lambda/functions/lambda_config.json"

# Load max_age from conf file:
with open(CONF_PATH, "r") as json_file:
    conf = json.load(json_file)
max_age = conf["headers"]["max_age"]


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
            {"key": "Cache-Control", "value": f"max-age={max_age}"}
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
