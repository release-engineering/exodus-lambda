import os
import subprocess
import tempfile

import boto3
import pytest
import requests


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
    parser.addoption(
        "--src-version",
        action="store",
        help="enable lambda source version validation",
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


@pytest.fixture
def src_version(request):
    # fetch exodus-lambda git version for version check
    # if src_version is unknown, version check will be skipped
    if request.config.getoption("--src-version"):
        version = request.config.getoption("--src-version")
    elif os.environ.get("CODEBUILD_RESOLVED_SOURCE_VERSION"):
        version = os.environ.get("CODEBUILD_RESOLVED_SOURCE_VERSION")
    else:
        return None
    return version


def mock_conf_file():
    temp_file = tempfile.NamedTemporaryFile(prefix="lambda_unittests_")

    os.environ["EXODUS_LAMBDA_CONF_FILE"] = temp_file.name

    test_env = os.environ.copy()

    test_env["PROJECT"] = "test"
    test_env["ENV_TYPE"] = "dev"
    test_env["EXODUS_CONFIG_CACHE_TTL"] = "2"
    test_env["EXODUS_CONNECT_TIMEOUT"] = "4"
    test_env["EXODUS_READ_TIMEOUT"] = "4"
    test_env["EXODUS_COOKIE_TTL"] = "720"
    test_env["EXODUS_HEADERS_MAX_AGE"] = "600"
    test_env["EXODUS_SECRET_ARN"] = "arn:aws:secretsmanager:example"
    test_env["EXODUS_KEY_ID"] = "K1MOU91G3N7WPY"
    test_env["ORIGIN_RESPONSE_LOGGER_LEVEL"] = "DEBUG"
    test_env["ORIGIN_REQUEST_LOGGER_LEVEL"] = "DEBUG"
    test_env["EXODUS_LAMBDA_VERSION"] = "fake version"
    test_env["EXODUS_INDEX_FILENAME"] = ".__exodus_autoindex"

    subprocess.run(
        ["envsubst"],
        stdin=open("./configuration/lambda_config.template", "r"),
        stdout=temp_file,
        check=True,
        env=test_env,
    )

    return temp_file


MOCK_LAMBDA_CONF_FILE = mock_conf_file()


def pytest_sessionfinish(session, exitstatus):
    # remove temp conf after whole test run finished
    MOCK_LAMBDA_CONF_FILE.close()


@pytest.fixture
def dummy_private_key():
    return """-----BEGIN RSA PRIVATE KEY-----
MIICWgIBAAKBgEku7kJh8jDweJCO73COmlSKlcw/A55kWLt245m0sQzx5P9eF3jG
NiDxYb9WZShyeckoS9B6i8+zX6g8OcnKmLXuavHyJpQXmE01ZpizCJiTcn7ihw/n
tPvzc+Ty1Haea30RPUvRUuhaqV+RjXSzCnTRkNiqH6YXLYbUIgfXN1rXAgMBAAEC
gYAkNCBQHK44ga3TLbLMBu/YJNroOMAsik3PJ4h+0IHJ+pyjrEOGTuAWOfN2OWI/
uSoAVnvy/bzOmlkXG/wmlKAo0QCDhieWM2Ss+rIkBjmSX8yO+K41Mu+BwOLS/Ynb
ch119R8L+TBS0pGt2tDBr5c+DJfDqcS+lhRJgoTenWkZ0QJBAIsxHUNyZV81mTP2
V5J0kViF/dtRDzQTjTvumWHcDj5R3VuQMrxQJS+8GTYO+6xP+W+oZIIY0TVUhuHg
WUb8q08CQQCGmQ/LnljQim73iSs6ew5VcIVghcMqhlXhZ6+LR0g7A0T2gNTjrGsS
UY9gdLOIpNFfWeUtWnTf7g3YUp41VNX5AkAJIFJD3tdIs9H0tz0srBnvjPGFFL6D
cpi7CjziTrRcX6+81iqNcE/P3mxkv/y+Yov/RzI32Xq2HXGuk7Am2GA/AkBO65J6
ZsdWx8TW+aPSL3MxH7/k36mW1pumheBFPy+YAou+Kb4qHN/PJul1uhfG6DUnvpMF
K8PZxUBy9cZ0KOEpAkA1b7cZpW40ZowMvAH6sF+7Ok1NFd+08AMXLiSJ6z7Sk29s
UrfAc2T6ZnfNC4qLIaDyo87CzVG/wk1Upr21z0YD
-----END RSA PRIVATE KEY-----"""


class VersionCheckingAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, expected_version):
        self.expected_version = expected_version
        super().__init__()

    def send(self, request, *args, **kwargs):
        request.headers["X-Exodus-Query"] = "1"
        response = super().send(request, *args, **kwargs)

        version = response.headers.get("X-Exodus-Version", None)
        if self.expected_version not in version:
            raise AssertionError(
                "Expected to run against version %s but server sent X-Exodus-Version: %s"
                % (self.expected_version, version)
            )
        return response


@pytest.fixture
def requests_session(src_version):
    session = requests.Session()
    if src_version:
        # we have an expected version, mount an adapter which
        # will check for that version
        session.mount("https://", VersionCheckingAdapter(src_version))
    return session
