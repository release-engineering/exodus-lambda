import json
import os


def generate_test_config(conf="configuration/lambda_config.json"):
    with open(conf, "r") as json_file:
        conf = json.load(json_file)

    # table
    conf["table"]["name"] = "test-table"
    conf["table"]["available_regions"] = [
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "ca-central-1",
        "eu-central-1",
        "eu-west-2",
        "eu-west-3",
        "eu-west-1",
        "sa-east-1",
        "ap-south-1",
        "ap-northeast-2",
        "ap-southeast-1",
        "ap-southeast-2",
        "ap-northeast-1",
    ]

    # logging
    conf["logging"]["formatters"]["default"][
        "format"
    ] = "[%(levelname)s] - %(message)s\n"
    conf["logging"]["loggers"]["origin-response"]["level"] = "DEBUG"
    conf["logging"]["loggers"]["origin-request"]["level"] = "DEBUG"
    conf["logging"]["loggers"]["default"]["level"] = "DEBUG"

    conf["config_table"]["name"] = "test-config-table"
    conf["config_table"]["cache_ttl"] = 2

    return conf


def mock_definitions():
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "test_data",
        "exodus-config.json",
    )
    with open(config_path) as f:
        exodus_config = json.load(f)

    return exodus_config
