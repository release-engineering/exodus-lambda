import os
import subprocess
import tempfile

import boto3
import pytest


def get_distribution_url(stack_name):
    url = None
    client = boto3.client("cloudformation")
    stack = client.describe_stacks(StackName=stack_name)
    data = stack["Stacks"][0]["Outputs"]
    for item in data:
        if item.get("OutputKey") == "Distribution":
            url = "https://" + item.get("OutputValue")
    if not url:
        pytest.skip("Test skipped because of invalid CDN url")
    return url


def pytest_addoption(parser):
    parser.addoption(
        "--cdn-test-url",
        action="store",
        help="enable integration tests against this CDN",
    )
    parser.addoption(
        "--lambda-stack",
        action="store",
        help="enable integration tests against this lambda stack",
    )


@pytest.fixture
def cdn_test_url(request):
    url = None
    cdn_url = request.config.getoption("--cdn-test-url")
    stack = request.config.getoption("--lambda-stack")

    if cdn_url:
        url = cdn_url
    elif stack:
        url = get_distribution_url(stack)
    else:
        pytest.skip("Test skipped without --cdn-test-url or --lambda-stack")
    return url


def mock_conf_file():
    temp_file = tempfile.NamedTemporaryFile(prefix="lambda_unittests_")

    os.environ["EXODUS_LAMBDA_CONF_FILE"] = temp_file.name

    test_env = os.environ.copy()

    test_env["PROJECT"] = "test"
    test_env["ENV_TYPE"] = "dev"
    test_env["EXODUS_CONFIG_CACHE_TTL"] = "2"
    test_env["ORIGIN_RESPONSE_LOGGER_LEVEL"] = "DEBUG"
    test_env["ORIGIN_REQUEST_LOGGER_LEVEL"] = "DEBUG"
    test_env["EXODUS_HEADERS_MAX_AGE"] = "600"

    cmd = "envsubst < ./configuration/lambda_config.template > {temp_path}"
    cmd = cmd.format(temp_path=temp_file.name)

    subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
        shell=True,
        env=test_env,
    )

    return temp_file


MOCK_LAMBDA_CONF_FILE = mock_conf_file()


def pytest_sessionfinish(session, exitstatus):
    # remove temp conf after whole test run finished
    MOCK_LAMBDA_CONF_FILE.close()
