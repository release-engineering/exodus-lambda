import json

import pytest

from exodus_lambda.functions.origin_response import OriginResponse

CONF_PATH = "exodus_lambda/functions/lambda_config.json"

# Load max_age from conf file:
with open(CONF_PATH, "r") as json_file:
    conf = json.load(json_file)
max_age = conf["headers"]["max_age"]


@pytest.mark.parametrize(
    "test_input",
    [
        "/some/repo/listing",
        "/some/repo/repodata/repomd.xml",
        "/some/repo/ostree/repo/refs/heads/ok/test",
    ],
)
def test_origin_response_valid_headers(
    test_input,
    expected=[{"key": "Cache-Control", "value": "max-age={}".format(max_age)}],
):
    event = {
        "Records": [
            {
                "cf": {
                    "request": {
                        "headers": {
                            "exodus-original-uri": [
                                {
                                    "key": "exodus-original-uri",
                                    "value": test_input,
                                }
                            ]
                        }
                    },
                    "response": {"headers": {}},
                }
            }
        ]
    }

    response = OriginResponse(conf_file=CONF_PATH).handler(event, context=None)
    assert response["headers"]["cache-control"] == expected


@pytest.mark.parametrize(
    "test_input",
    ["/some/repo/some-rpm.rpm", "/some/repo/ostree/repo/refs/heads/nope"],
)
def test_origin_response_empty_headers(test_input, expected={}):
    event = {
        "Records": [
            {"cf": {"request": {"headers": {}}, "response": {"headers": {}}}}
        ]
    }

    response = OriginResponse(conf_file=CONF_PATH).handler(event, context=None)
    assert response["headers"] == expected


def test_origin_response_missing_headers():
    event = {"Records": [{"cf": {"request": {}, "response": {}}}]}

    response = OriginResponse(conf_file=CONF_PATH).handler(event, context=None)
    assert response == {}
