import json
import os


class LambdaBase(object):
    def __init__(self, conf_file="lambda_config.json"):
        self._conf_file = conf_file
        self._conf = None

    @property
    def conf(self):
        if not self._conf:
            with open(self._conf_file, "r") as json_file:
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

    def handler(self, event, context):
        raise NotImplementedError
