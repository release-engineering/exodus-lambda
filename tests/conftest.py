import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--cdn-test-url",
        action="store",
        help="enable integration tests against this CDN",
    )


@pytest.fixture
def cdn_test_url(request):
    out = request.config.getoption("--cdn-test-url")
    if not out:
        pytest.skip("Test skipped without --cdn-test-url")
    return out
