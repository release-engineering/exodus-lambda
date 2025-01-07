# More in depth tests for alias resolution.
from collections import namedtuple

import pytest

from exodus_lambda.functions.origin_request import OriginRequest

from ..test_utils.utils import generate_test_config

TEST_CONF = generate_test_config()

Alias = namedtuple("Alias", ["src", "dest", "exclude_paths"])


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


@pytest.mark.parametrize(
    "uri, expected_uri, ignore_exclusions, aliases",
    [
        (
            "/origin/path/dir/filename.ext",
            "/origin/path/dir/filename.ext",
            False,
            [
                {
                    "src": "/origin/path",
                    "dest": "/alias",
                    "exclude_paths": ["/dir/"],
                }
            ],
        ),
        (
            "/origin/path/dir/filename.ext",
            "/alias/dir/filename.ext",
            False,
            [
                {
                    "src": "/origin/path",
                    "dest": "/alias",
                    "exclude_paths": ["/banana/"],
                }
            ],
        ),
        (
            "/origin/path/c/dir/filename.ext",
            "/second/step/c/dir/filename.ext",
            False,
            [
                {
                    "src": "/origin/path",
                    "dest": "/first/step",
                    "exclude_paths": ["/a/"],
                },
                {"src": "/first", "dest": "/second", "exclude_paths": ["/b/"]},
                {"src": "/second", "dest": "/third", "exclude_paths": ["/c/"]},
            ],
        ),
        (
            "/origin/path/rhel7/dir/filename.ext",
            "/aliased/path/rhel7/dir/filename.ext",
            False,
            [
                {
                    "src": "/origin",
                    "dest": "/aliased",
                    "exclude_paths": ["/rhel[89]/"],
                },
            ],
        ),
        (
            "/origin/path/rhel9/dir/filename.ext",
            "/origin/path/rhel9/dir/filename.ext",
            False,
            [
                {
                    "src": "/origin",
                    "dest": "/aliased",
                    "exclude_paths": ["/rhel[89]/"],
                },
            ],
        ),
        (
            "/origin/path/rhel9/dir/filename.ext",
            "/aliased/path/rhel9/dir/filename.ext",
            True,
            [
                {
                    "src": "/origin",
                    "dest": "/aliased",
                    "exclude_paths": ["/rhel9/"],
                },
            ],
        ),
        (
            "/origin/path/rhel9/dir/filename.ext",
            "/aliased/path/rhel9/dir/filename.ext",
            True,
            [
                {
                    "src": "/origin",
                    "dest": "/aliased",
                    "exclude_paths": ["/rhel7/"],
                },
            ],
        ),
    ],
    ids=[
        "excluded",
        "not excluded",
        "multilevel",
        "regex not excluded",
        "regex excluded",
        "exclusion ignored matching",
        "exclusion ignored no match",
    ],
)
def test_alias_exclusions(uri, expected_uri, ignore_exclusions, aliases):
    """Paths exactly matching an alias can be resolved."""

    req = OriginRequest(conf_file=TEST_CONF)

    assert req.uri_alias(uri, aliases, ignore_exclusions) == expected_uri
