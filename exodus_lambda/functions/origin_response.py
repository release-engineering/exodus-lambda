import os
from base64 import b64encode

from .base import LambdaBase

CONF_FILE = os.environ.get("EXODUS_LAMBDA_CONF_FILE") or "lambda_config.json"


class OriginResponse(LambdaBase):
    def __init__(self, conf_file=CONF_FILE):
        super().__init__("origin-response", conf_file)

    def strip_response_headers(self, response):
        # Remove some headers which should not be in the response,
        # according to 'strip_headers' config item.
        prefixes = self.conf.get("strip_headers") or [
            "x-amz-meta-",
            "x-amz-replication-status",
            "x-amz-server-side-encryption",
            "x-amz-version-id",
        ]
        headers = response.get("headers") or {}
        to_remove = [
            key
            for key in headers.keys()
            if any([key.startswith(p) for p in prefixes])
        ]
        for key in to_remove:
            del headers[key]

    def handler(self, event, context):
        # pylint: disable=unused-argument

        request = event["Records"][0]["cf"]["request"]
        response = event["Records"][0]["cf"]["response"]

        self.logger.debug(
            "Incoming event for origin_response",
            extra={"request": request, "response": response},
        )

        if "headers" in request and "want-repr-digest" in request["headers"]:
            sum_hex = request["uri"].replace("/", "", 1)
            sum_b64 = b64encode(bytes.fromhex(sum_hex)).decode()
            response["headers"]["repr-digest"] = [
                {"key": "Repr-Digest", "value": f"sha-256=:{sum_b64}:"}
            ]

        if "headers" in request and "x-exodus-query" in request["headers"]:
            self.set_lambda_version(response)

        try:
            original_uri = request["headers"]["exodus-original-uri"][0][
                "value"
            ]

        except KeyError:
            self.logger.debug(
                "Could not read exodus-original-uri from response",
                exc_info=True,
            )
            original_uri = None

        if original_uri:
            self.set_cache_control(original_uri, response)

        self.strip_response_headers(response)

        self.logger.debug(
            "Completed response processing",
            extra={"request": request, "response": response},
        )
        return response


# Make handler available at module level
lambda_handler = OriginResponse().handler  # pylint: disable=invalid-name
