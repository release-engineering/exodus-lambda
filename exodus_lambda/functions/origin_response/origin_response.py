import json
import logging
import re

LOG = logging.getLogger("origin-response")


class LambdaClient(object):
    def __init__(self, conf_file="lambda_config.json"):
        self._conf_file = conf_file
        self._conf = None

    @property
    def conf(self):
        if not self._conf:
            with open(self._conf_file, "r") as json_file:
                self._conf = json.load(json_file)

        return self._conf

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
lambda_handler = LambdaClient().handler  # pylint: disable=invalid-name
