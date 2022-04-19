import json
import os
from datetime import datetime, timedelta, timezone

from exodus_lambda.functions.signer import Signer


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
