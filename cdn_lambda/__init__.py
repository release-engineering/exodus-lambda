from cdn_lambda.functions.map_to_s3.map_to_s3 import (
    lambda_handler as origin_request,
)

# All lambda functions should be exported from this module.
# Name them after the trigger with which they're intended to be used.

__all__ = ["origin_request"]
