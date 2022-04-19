import json
import logging
import logging.config
import os
import re

from .config import (
    DictLambdaConfig,
    EnvironmentLambdaConfig,
    LambdaConfig,
    MixedLambdaConfig,
)


class LambdaBase(object):
    def __init__(self, logger_name="default", conf_file=None):
        # conf_file defaults to an empty dict which means that we only read config
        # from env vars, but the lambda instances actually deployed are passing
        # a non-empty conf_file at the moment. This will eventually be removed
        # entirely.
        self._conf_file = conf_file or {}
        self._conf = None
        self._logger_name = logger_name
        self._logger = None

    @property
    def conf(self) -> LambdaConfig:
        if not self._conf:
            # We currently support config via environment variables or
            # a config file. Config file support is being retained only until
            # deployments have had a chance to migrate to env vars, after which
            # we'll only support env vars here.
            env_conf = EnvironmentLambdaConfig()

            if isinstance(self._conf_file, dict):
                dict_conf = DictLambdaConfig(self._conf_file)
            else:
                with open(self._conf_file, "r", encoding="UTF-8") as json_file:
                    dict_conf = DictLambdaConfig(json.load(json_file))

            self._conf = MixedLambdaConfig(dict_conf, env_conf)

        return self._conf

    @property
    def region(self) -> str:
        # Use environment region if among available regions.
        # Otherwise, default to first available region listed.
        env_region = os.environ.get("AWS_REGION")
        if env_region in self.conf.item_table_regions:
            return env_region
        return self.conf.item_table_regions[0]

    @property
    def logger(self):
        if not self._logger:
            log_conf = self.conf.logging_config
            logging.config.dictConfig(log_conf)
            root_logger = logging.getLogger()
            if log_conf and root_logger.handlers:
                formatter_str = log_conf["formatters"]["default"]["format"]
                formatter_date = log_conf["formatters"]["default"]["datefmt"]
                formatter = logging.Formatter(formatter_str, formatter_date)
                root_logger.handlers[0].setFormatter(formatter)
            self._logger = logging.getLogger(self._logger_name)
        return self._logger

    @property
    def max_age(self):
        return self.conf.cache_control_max_age

    @property
    def lambda_version(self):
        return self.conf.lambda_version

    def set_lambda_version(self, response):
        response.setdefault("headers", {})["x-exodus-version"] = [
            {"key": "X-Exodus-Version", "value": self.lambda_version}
        ]

    def set_cache_control(self, uri, response):
        max_age_pattern_whitelist = [
            ".+/PULP_MANIFEST",
            ".+/listing",
            ".+/repodata/repomd.xml",
            ".+/ostree/repo/refs/heads/.*/.*",
        ]

        for pattern in max_age_pattern_whitelist:
            if re.match(pattern, uri):
                response["headers"]["cache-control"] = [
                    {
                        "key": "Cache-Control",
                        "value": f"max-age={self.max_age}",
                    }
                ]
                self.logger.info("Cache-Control header added for '%s'", uri)

    def handler(self, event, context):
        raise NotImplementedError
