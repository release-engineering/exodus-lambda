"""fakefront: run exodus-lambda in a local Cloudfront-like environment.

Provides a WSGI app which can be invoked by e.g. gunicorn.

Primarily intended for use against a localstack environment, whose URL
should be set in the EXODUS_AWS_ENDPOINT_URL environment variable.

While it's likely possible to run this against real AWS services also,
your S3 bucket would have to be unsecured, which is not recommended.
"""
from .config import ensure_config


def new_app():
    # Ensure various config is in place before starting the app.
    # This will do various things including:
    #
    # - generate a temporary lambda_config.json
    # - generate a public/private key pair and populate the private
    #   key into a secret
    # - fill in some default values of AWS env vars to make setup
    #   a bit easier
    #
    ensure_config()

    # Note that import of wsgi is delayed until now because some
    # code in exodus-lambda will read config at import time, so
    # the import must not happen until after ensure_config().
    from .wsgi import Wsgi

    return Wsgi()


application = new_app()
