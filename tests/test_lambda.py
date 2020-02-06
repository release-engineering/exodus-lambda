from cdn_lambda.lambda_functions import lambda_handler


def test_lambda_handler():
    assert lambda_handler({}, {})["status"] == "501"
