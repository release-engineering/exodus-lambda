import pytest

import logging

from exodus_lambda.functions.base import LambdaBase
from test_utils.utils import generate_test_config

CONF_PATH = "configuration/lambda_config.json"
TEST_CONF = generate_test_config(CONF_PATH)


def test_base_handler():
    with pytest.raises(NotImplementedError):
        LambdaBase(conf_file=CONF_PATH).handler(event=None, context=None)


@pytest.mark.parametrize(
    "env_var,exp_var",
    [
        ("us-south-7", "us-east-1"),
        ("ap-southeast-2", "ap-southeast-2"),
        ("ap-northeast-3", "us-east-1"),
    ],
    ids=["fake", "available", "unavailable"],
)
def test_base_region(env_var, exp_var, monkeypatch):
    """Ensure correct regions are selected for various inputs"""
    base = LambdaBase(conf_file=TEST_CONF)

    # Environment variable is set
    monkeypatch.setenv("AWS_REGION", env_var)
    assert base.region == exp_var

    # Environment variable is unset
    monkeypatch.delenv("AWS_REGION")
    assert base.region == "us-east-1"


def test_logger_config(caplog):
    base_obj = LambdaBase(conf_file=TEST_CONF)

    with caplog.at_level(logging.DEBUG):
        base_obj.logger.debug("debug message")
        base_obj.logger.info("info message")
        base_obj.logger.warning("warning message")
    assert "[DEBUG] - debug message\n" in caplog.text
    assert "[INFO] - info message\n" in caplog.text
    assert "[WARNING] - warning message\n" in caplog.text


def test_root_logger_without_handlers(caplog):
    """
    A root logger without handlers should not cause the program to crash.
    """
    root_logger = logging.getLogger()
    root_logger.handlers = []
    base_obj = LambdaBase(conf_file=TEST_CONF)
    base_obj.logger.warning("warning message")
    assert root_logger.handlers == []
    assert "warning message" not in caplog.text
