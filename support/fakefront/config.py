import atexit
import json
import logging
import os
from subprocess import check_call, check_output
from tempfile import NamedTemporaryFile

import boto3

LOG = logging.getLogger("fakefront")

THIS_DIR = os.path.dirname(__file__)
MK_CONFIG = os.path.join(THIS_DIR, "../../scripts/mk-config")
KEY_DIR = os.path.expanduser("~/.config/exodus-fakefront")


def ensure_config_file():
    """Ensure that a lambda_config.json file exists and is pointed to
    by the EXODUS_LAMBDA_CONF_FILE environment variable.

    A new temporary config file will be generated. The config file's
    contents can be controlled by the environment variables listed
    within scripts/mk-config.
    """
    config_file = NamedTemporaryFile(
        mode="wt", prefix="fakefront", delete=False
    )
    atexit.register(os.remove, config_file.name)

    config_json = check_output([MK_CONFIG], env=os.environ, text=True)
    config_file.write(config_json)
    config_file.flush()

    LOG.info("fakefront: using config at %s", config_file.name)
    os.environ["EXODUS_LAMBDA_CONF_FILE"] = config_file.name


def ensure_keypair():
    """Ensures a public, private keypair exists which can be used for
    signing requests.

    Returns the paths to the (public, private) key files.
    """
    os.makedirs(KEY_DIR, exist_ok=True)

    public_key = os.path.join(KEY_DIR, "pubkey.pem")
    private_key = os.path.join(KEY_DIR, "privatekey.pem")

    # openssl genrsa -out private_key.pem 2048
    if not os.path.exists(private_key):
        check_call(["openssl", "genrsa", "-out", private_key, "2048"])
        LOG.info("fakefront: created private key: %s", private_key)

    if not os.path.exists(public_key):
        check_call(
            [
                "openssl",
                "rsa",
                "-pubout",
                "-in",
                private_key,
                "-out",
                public_key,
            ]
        )
        LOG.info("fakefront: created public key: %s", public_key)

    return (public_key, private_key)


def ensure_aws_config():
    """Check and/or set various environment variables influencing
    the connections between exodus-lambda & AWS.
    """

    if os.environ.get("EXODUS_AWS_ENDPOINT_URL") and not os.environ.get(
        "EXODUS_FAKEFRONT_BUCKET_URL"
    ):
        # If the user has set an AWS endpoint and they haven't set any bucket URL,
        # we'll assume they're using a localstack in the default configuration as
        # provisioned by exodus-gw dev env, which means the bucket URL is the endpoint
        # plus bucket name.
        default = os.path.join(
            os.environ["EXODUS_AWS_ENDPOINT_URL"], "my-bucket"
        )
        os.environ["EXODUS_FAKEFRONT_BUCKET_URL"] = default

        LOG.info("fakefront: defaulted bucket URL to %s", default)

    if not os.environ.get("EXODUS_FAKEFRONT_BUCKET_URL"):
        raise RuntimeError(
            "Must set EXODUS_AWS_ENDPOINT_URL or EXODUS_FAKEFRONT_BUCKET_URL."
        )

    if os.environ.get("EXODUS_AWS_ENDPOINT_URL"):
        # Just to make things a bit easier in the localstack case, we'll set
        # credentials to dummy values automatically. This can be done since the
        # creds aren't really used, and it avoids the requirement for the
        # caller to have a valid ~/.aws/credentials .
        for varname in (
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN",
        ):
            if varname not in os.environ:
                os.environ[varname] = "dummy"


def ensure_secret():
    """Ensure that a secret exists holding a private key usable for signing,
    and ensure the secret is pointed to by the EXODUS_SECRET_ARN
    environment variable.
    """
    if os.environ.get("EXODUS_SECRET_ARN"):
        # Secret is already set explicitly, don't touch anything.
        return

    if os.environ.get("EXODUS_KEY_ID") != "FAKEFRONT":
        # Not using the fake key, don't touch anything.
        return

    # There is currently no secret defined and we're using the fake key.
    # To make setup easier, we support creating the secret on the fly.
    sm_client = boto3.client(
        "secretsmanager",
        region_name="us-east-1",
        endpoint_url=os.environ.get("EXODUS_AWS_ENDPOINT_URL") or None,
    )

    (_, privkey) = ensure_keypair()

    secret = json.dumps({"cookie_key": open(privkey).read()})

    try:
        # create it
        arn = sm_client.create_secret(
            Name="fakefront-key",
            SecretString=secret,
        )["ARN"]
    except sm_client.exceptions.ResourceExistsException:
        # already existed, so update it instead
        arn = sm_client.update_secret(
            SecretId="fakefront-key",
            SecretString=secret,
        )["ARN"]

    os.environ["EXODUS_SECRET_ARN"] = arn
    LOG.info("Created/updated %s from %s", arn, privkey)


def ensure_config():
    """Ensures various configuration is in place.

    This doesn't return anything and is called only for its side-effects.
    It should be called once, before creation of the fakefront wsgi app."""

    # Set up some basic logging just during our configuration; we expect
    # the lambda code to reconfigure loggers later on.
    logging.basicConfig(level=logging.INFO)

    ensure_aws_config()
    ensure_secret()
    ensure_config_file()
