import json


def generate_test_config(conf="configuration/lambda_config.json"):
    with open(conf, "r") as json_file:
        conf = json.load(json_file)
    conf["logging"]["formatters"]["default"][
        "format"
    ] = "[%(levelname)s] - %(message)s\n"
    conf["logging"]["loggers"]["origin-response"]["level"] = "DEBUG"
    conf["logging"]["loggers"]["origin-request"]["level"] = "DEBUG"
    conf["logging"]["loggers"]["default"]["level"] = "DEBUG"
    return conf
