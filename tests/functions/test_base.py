import pytest

from exodus_lambda.functions.base import LambdaBase

CONF_PATH = "exodus_lambda/functions/lambda_config.json"


def test_base():
    with pytest.raises(NotImplementedError):
        LambdaBase(conf_file=CONF_PATH).handler(event=None, context=None)
