import json


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

    def handler(self, event, context):
        raise NotImplementedError
