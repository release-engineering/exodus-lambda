from exodus_lambda.functions.origin_request import (
    lambda_handler as origin_request,
)

from exodus_lambda.functions.origin_response import (
    lambda_handler as origin_response,
)

# All lambda functions should be exported from this module.
# Name them after the trigger with which they're intended to be used.

__all__ = ["origin_request", "origin_response"]
