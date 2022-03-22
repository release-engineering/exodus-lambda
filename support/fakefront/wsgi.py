import os
from typing import Any, Callable, Dict, Iterable, List, Tuple

import requests

from exodus_lambda.functions.origin_request import OriginRequest
from exodus_lambda.functions.origin_response import OriginResponse

from .lambdaio import LambdaInput, LambdaOutput

BUCKET_URL = os.environ["EXODUS_FAKEFRONT_BUCKET_URL"]

# Type hints for the wsgi start_response callable.
StartResponseHeaders = List[Tuple[str, str]]
StartResponse = Callable[[str, StartResponseHeaders], None]


class Wsgi:
    """Main WSGI callable serving the fakefront app.

    This object implements the basic cloudfront behaviors required for
    exodus-lambda, including:

    - invoke origin-request lambda
    - do request to S3
    - invoke origin-response lambda
    - give response to caller based on outcome of above
    """

    def __init__(self):
        self.origin_request = OriginRequest()
        self.origin_response = OriginResponse()
        self.s3_session = requests.Session()

    def __call__(
        self, environ: Dict[str, Any], start_response: StartResponse
    ) -> Iterable[bytes]:
        context = {}

        # 1. Take the request information from the WSGI environment and
        # transform it into a cloudfront event usable as lambda input.
        req = LambdaInput(environ)

        # 2. Pass the event through origin-request handler.
        origin_request_out = LambdaOutput(
            self.origin_request.handler(req.origin_request, context)
        )

        # 3. If origin-request handler already produced a response, just
        # return it.
        if origin_request_out.status:
            start_response(
                origin_request_out.wsgi_status,
                origin_request_out.wsgi_headers,
            )
            return origin_request_out.wsgi_body

        # 4. Allow the request to proceed to S3.
        s3_response = self.do_s3_request(origin_request_out)

        # 5. Pass the S3 response event through origin-response handler.
        # Note that the raw output from origin-request is passed into
        # origin-response here.
        origin_response_in = LambdaInput(
            environ,
            origin_request_out.raw,
            s3_response,
        )
        origin_response_out = LambdaOutput(
            self.origin_response.handler(
                origin_response_in.origin_response, context
            )
        )

        # 6. Respond with whatever status & headers came from origin-response,
        # plus the bytes from S3.
        start_response(
            origin_response_out.wsgi_status, origin_response_out.wsgi_headers
        )
        return origin_response_out.wsgi_body or s3_response.iter_content()

    def do_s3_request(self, origin_request_out: LambdaOutput):
        """Do a request to S3 bucket based on the value returned from
        the origin-request lambda.
        """
        components = [BUCKET_URL, origin_request_out.uri]

        if origin_request_out.querystring:
            components.extend(["?", origin_request_out.querystring])

        url = "".join(components)

        # These should be the only allowed methods
        assert origin_request_out.method in ("GET", "HEAD")

        return self.s3_session.request(
            origin_request_out.method, url, stream=True
        )
