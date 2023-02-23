import json
import logging
import os

import pytest

from exodus_lambda.functions.base import LambdaBase

from ..test_utils.utils import generate_test_config

CONF_FILE = os.environ.get("EXODUS_LAMBDA_CONF_FILE")
TEST_CONF = generate_test_config()


def test_base_handler():
    with pytest.raises(NotImplementedError):
        LambdaBase(conf_file=CONF_FILE).handler(event=None, context=None)


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
    log = base_obj.logger

    log.setLevel(logging.DEBUG)

    log.debug("debug message")
    assert "debug message" in caplog.text

    log.info("info message")
    assert "info message" in caplog.text

    log.warning("warning message")
    assert "warning message" in caplog.text


def test_root_logger_without_handlers(caplog):
    """A root logger without handlers should not cause the program to crash."""

    root_logger = logging.getLogger()
    root_logger.handlers = []
    base_obj = LambdaBase(conf_file=TEST_CONF)
    base_obj.logger.warning("warning message")
    assert root_logger.handlers == []
    assert "warning message" not in caplog.text


def test_json_handler_stack_info(caplog):
    base_obj = LambdaBase(conf_file=TEST_CONF)
    base_obj.logger.exception("oops", stack_info=True)
    assert '"stack_info": "Stack (most recent call last)' in caplog.text


def test_json_handler_fallback(caplog):
    """Ensure string formatting remains supported."""

    base_obj = LambdaBase(conf_file=TEST_CONF)
    base_obj.conf["logging"]["formatters"]["default"][
        "format"
    ] = "%(levelname)s - %(message)s"
    base_obj.logger.info("testing 123")
    assert caplog.text == "INFO - testing 123\n"


def test_json_handler_invalid_json_string(caplog):
    base_obj = LambdaBase(conf_file=TEST_CONF)
    base_obj.conf["logging"]["formatters"]["default"][
        "format"
    ] = "{'level':'levelname','message':'message'}"

    with pytest.raises(json.JSONDecodeError):
        base_obj.logger.info("testing 123")

    # Formatting should remain logging default.
    assert (
        "Unable to load JSON format: {'level':'levelname','message':'message'}"
        in caplog.text
    )
