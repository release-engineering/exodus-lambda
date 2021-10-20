import json
import logging
import logging.config
import os


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
                for conf_file in [
                    self._conf_file,
                    os.path.join(
                        os.path.dirname(
                            os.path.dirname(os.path.dirname(__file__))
                        ),
                        "configuration",
                        "lambda_config.json",
                    ),
                ]:
                    if os.path.exists(conf_file):
                        with open(conf_file, "r") as json_file:
                            self._conf = json.load(json_file)
                        break
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
                formatter_str = log_conf["formatters"]["default"]["format"]
                formatter_date = log_conf["formatters"]["default"]["datefmt"]
                formatter = logging.Formatter(formatter_str, formatter_date)
                root_logger.handlers[0].setFormatter(formatter)
            self._logger = logging.getLogger(self._logger_name)
        return self._logger

    def handler(self, event, context):
        raise NotImplementedError
