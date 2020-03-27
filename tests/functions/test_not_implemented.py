from exodus_lambda.functions.not_implemented import lambda_handler


def test_lambda_handler():
    assert lambda_handler({}, {})["status"] == "501"
