import json
import os
from datetime import datetime, timedelta, timezone

from exodus_lambda.functions.signer import Signer

CONF_FILE = os.environ.get("EXODUS_LAMBDA_CONF_FILE")


def generate_test_config(conf=CONF_FILE):
    with open(conf, "r") as json_file:
        conf = json.load(json_file)

    # tables
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
    conf["config_table"]["name"] = "test-config-table"

    # logging
    conf["logging"]["loggers"]["origin-response"]["level"] = "DEBUG"
    conf["logging"]["loggers"]["origin-request"]["level"] = "DEBUG"
    conf["logging"]["loggers"]["default"]["level"] = "DEBUG"

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


def generate_test_cookies():
    # Env var for using signed cookies
    key = os.environ.get("EXODUS_CDN_PRIVATE_KEY")
    key_id = os.environ.get("EXODUS_CDN_KEY_ID")

    if not key or not key_id:
        # envvar absent, requests will not be signed
        return {}

    expiration = datetime.now(timezone.utc) + timedelta(hours=1)
    signer = Signer(key, key_id)
    cookies = signer.cookies_for_policy(
        append="",
        resource="https://*",
        date_less_than=expiration,
    )
    return {item.split("=")[0]: item.split("=")[1] for item in cookies}
