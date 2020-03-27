from exodus_lambda import origin_request


def test_have_origin_request():
    """exodus_lambda should export a function named origin_request"""

    assert callable(origin_request)
