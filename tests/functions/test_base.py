import pytest

from exodus_lambda.functions.base import LambdaBase

CONF_PATH = "configuration/lambda_config.json"


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
    base = LambdaBase(conf_file=CONF_PATH)

    # Environment variable is set
    monkeypatch.setenv("AWS_REGION", env_var)
    assert base.region == exp_var

    # Environment variable is unset
    monkeypatch.delenv("AWS_REGION")
    assert base.region == "us-east-1"
