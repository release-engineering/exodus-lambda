import json
from base64 import b64encode

from .base import LambdaBase


class OriginResponse(LambdaBase):
    def __init__(self, conf_file="lambda_config.json"):
        super().__init__("origin-response", conf_file)

    def handler(self, event, context):
        # pylint: disable=unused-argument

        request = event["Records"][0]["cf"]["request"]
        response = event["Records"][0]["cf"]["response"]

        self.logger.info(
            "The request value for origin_response beginning is '%s'",
            json.dumps(request, indent=4, sort_keys=True),
        )
        self.logger.info(
            "The response value for origin_response beginning is '%s'",
            json.dumps(response, indent=4, sort_keys=True),
        )

        if "headers" in request and "want-digest" in request["headers"]:
            sum_hex = request["uri"].replace("/", "", 1)
            sum_b64 = b64encode(bytes.fromhex(sum_hex)).decode()
            response["headers"]["digest"] = [
                {"key": "Digest", "value": f"id-sha-256={sum_b64}"}
            ]

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

        return response


# Make handler available at module level
lambda_handler = OriginResponse().handler  # pylint: disable=invalid-name
