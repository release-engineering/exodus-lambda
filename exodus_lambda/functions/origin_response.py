import re
from base64 import b64encode

from .base import LambdaBase


class OriginResponse(LambdaBase):
    def __init__(self, conf_file="lambda_config.json"):
        super().__init__("origin-response", conf_file)

    def handler(self, event, context):
        # pylint: disable=unused-argument

        request = event["Records"][0]["cf"]["request"]
        response = event["Records"][0]["cf"]["response"]

        if "headers" in request and "want-digest" in request["headers"]:
            sum_hex = request["uri"].replace("/", "", 1)
            sum_b64 = b64encode(bytes.fromhex(sum_hex)).decode()
            response["headers"]["digest"] = [
                {"key": "Digest", "value": f"id-sha-256={sum_b64}"}
            ]

        max_age = self.conf["headers"]["max_age"]
        max_age_pattern_whitelist = [
            ".+/PULP_MANIFEST",
            ".+/listing",
            ".+/repodata/repomd.xml",
            ".+/ostree/repo/refs/heads/.*/.*",
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
            for pattern in max_age_pattern_whitelist:
                if re.match(pattern, original_uri):
                    response["headers"]["cache-control"] = [
                        {"key": "Cache-Control", "value": f"max-age={max_age}"}
                    ]
                    self.logger.info(
                        "Cache-Control header added for '%s'", original_uri
                    )

        return response


# Make handler available at module level
lambda_handler = OriginResponse().handler  # pylint: disable=invalid-name
