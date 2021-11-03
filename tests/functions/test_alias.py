# More in depth tests for alias resolution.
from collections import namedtuple

from exodus_lambda.functions.origin_request import OriginRequest

from ..test_utils.utils import generate_test_config

CONF_PATH = "configuration/lambda_config.json"
TEST_CONF = generate_test_config(CONF_PATH)

Alias = namedtuple("Alias", ["src", "dest"])


def test_alias_single():
    """Each alias is only applied a single time."""

    req = OriginRequest(conf_file=TEST_CONF)

    aliases = [
        {"src": "/foo/bar", "dest": ""},
        {"src": "/baz", "dest": "/quux"},
    ]

    # Only the first layer of /foo/bar ends up being resolved.
    assert (
        req.uri_alias("/foo/bar/foo/bar/baz/somefile", aliases)
        == "/foo/bar/baz/somefile"
    )


def test_alias_boundary():
    """Aliases are only resolved at path boundaries."""

    req = OriginRequest(conf_file=TEST_CONF)

    aliases = [{"src": "/foo/bar", "dest": "/"}]

    # /foo/bar should not be resolved since it's not followed by /.
    assert req.uri_alias("/foo/bar-somefile", aliases) == "/foo/bar-somefile"


def test_alias_equal():
    """Paths exactly matching an alias can be resolved."""

    req = OriginRequest(conf_file=TEST_CONF)

    aliases = [{"src": "/foo/bar", "dest": "/quux"}]

    assert req.uri_alias("/foo/bar", aliases) == "/quux"
