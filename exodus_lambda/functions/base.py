import json
import logging
import logging.config
import os
import re

from .json_logging import JsonFormatter


class LambdaBase(object):
    def __init__(self, logger_name="default", conf_file="lambda_config.json"):
        self._conf_file = conf_file
        self._conf = None
        self._logger_name = logger_name
        self._logger = None

    @property
    def conf(self):
        if not self._conf:
            if isinstance(self._conf_file, dict):
                self._conf = self._conf_file
            else:
                with open(self._conf_file, "r", encoding="UTF-8") as json_file:
                    self._conf = json.load(json_file)
        return self._conf

    @property
    def region(self):
        # Use environment region if among available regions.
        # Otherwise, default to first available region listed.
        env_region = os.environ.get("AWS_REGION")
        if env_region in self.conf["table"]["available_regions"]:
            return env_region
        return self.conf["table"]["available_regions"][0]

    @property
    def logger(self):
        if not self._logger:
            log_conf = self.conf.get("logging", {})
            logging.config.dictConfig(log_conf)
            root_logger = logging.getLogger()
            if log_conf and root_logger.handlers:
                datefmt = log_conf["formatters"]["default"].get("datefmt")
                formatter = JsonFormatter(datefmt=datefmt)
                root_logger.handlers[0].setFormatter(formatter)
            self._logger = logging.getLogger(self._logger_name)
            self._logger.info("Initializing logger...")
        return self._logger

    @property
    def max_age(self):
        return self.conf["headers"]["max_age"]

    @property
    def lambda_version(self):
        return self.conf["lambda_version"]

    @property
    def index(self):
        return self.conf["index_filename"]

    @property
    def mirror_reads(self):
        if str(self.conf.get("mirror_reads", "true")).lower() in (
            "0",
            "false",
        ):
            return False
        return True

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

    def handler(self, event, context):
        raise NotImplementedError
