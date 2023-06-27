import copy
import json
import logging
import os

import pytest
from freezegun import freeze_time

from exodus_lambda.functions.base import LambdaBase

from ..test_utils.utils import generate_test_config

CONF_FILE = os.environ.get("EXODUS_LAMBDA_CONF_FILE")
TEST_CONF = generate_test_config()
MOCKED_DT = "2023-04-26 14:43:13.570034+00:00"


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


def test_json_logger_stack_info(caplog):
    base_obj = LambdaBase(conf_file=TEST_CONF)
    base_obj.logger.exception("oops", stack_info=True)
    assert '"stack_info": "Stack (most recent call last)' in caplog.text


@freeze_time(MOCKED_DT)
def test_json_logger_timestamp(caplog):
    LambdaBase(conf_file=TEST_CONF).logger.info("Works!")

    # Logged timestamp should show milliseconds by default
    assert [json.loads(log) for log in caplog.text.splitlines()] == [
        {
            "level": "INFO",
            "time": "2023-04-26 14:43:13.570",
            "aws-request-id": None,
            "message": "Initializing logger...",
            "logger": "default",
            "request": None,
            "response": None,
        },
        {
            "level": "INFO",
            "time": "2023-04-26 14:43:13.570",
            "aws-request-id": None,
            "message": "Works!",
            "logger": "default",
            "request": None,
            "response": None,
        }
    ]


@freeze_time(MOCKED_DT)
def test_json_logger_configurable_datefmt(caplog):
    """Ensure logger's datefmt is configurable"""

    new_datefmt = "%H:%M on %A, %B %d, %Y"

    conf = copy.deepcopy(TEST_CONF)
    conf["logging"]["formatters"]["default"]["datefmt"] = new_datefmt

    LambdaBase(conf_file=conf).logger.info("Works!")
    # Logged timestamp should be formatted as new_datefmt
    assert [json.loads(log) for log in caplog.text.splitlines()] == [
        {
            "level": "INFO",
            "time": "14:43 on Wednesday, April 26, 2023",
            "aws-request-id": None,
            "message": "Initializing logger...",
            "logger": "default",
            "request": None,
            "response": None,
        },
        {
            "level": "INFO",
            "time": "14:43 on Wednesday, April 26, 2023",
            "aws-request-id": None,
            "message": "Works!",
            "logger": "default",
            "request": None,
            "response": None,
        }
    ]
