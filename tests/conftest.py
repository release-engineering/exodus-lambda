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
