import logging
import re

from .base import LambdaBase

LOG = logging.getLogger("origin-response")


class OriginResponse(LambdaBase):
    def handler(self, event, context):
        # pylint: disable=unused-argument

        request = event["Records"][0]["cf"]["request"]
        response = event["Records"][0]["cf"]["response"]

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
            LOG.debug(
                "Could not read exodus-original-uri from response",
                exc_info=True,
            )
            original_uri = None

        if original_uri:
            for pattern in max_age_pattern_whitelist:
                if re.match(pattern, original_uri):
                    response["headers"]["cache-control"] = [
                        {
                            "key": "Cache-Control",
                            "value": f"max-age={max_age}",
                        }
                    ]
                    LOG.info(
                        "Cache-Control header added for '%s'", original_uri
                    )

        return response


# Make handler available at module level
lambda_handler = OriginResponse().handler  # pylint: disable=invalid-name
