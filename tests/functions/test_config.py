from exodus_lambda.functions.config import EnvironmentLambdaConfig

# Tests for config classes.
#
# The classes are near 100% covered by other tests. Only edge cases
# not reached elsewhere are covered here.


def test_default_region():
    cfg = EnvironmentLambdaConfig()
    assert cfg.item_table_regions == ["us-east-1"]


def test_logger_levels(monkeypatch, caplog):
    """EXODUS_LOGGER_* environment variables are parsed to set log levels."""

    monkeypatch.setenv("EXODUS_LOGGER_WHATEVER", "foo bar INFO")
    monkeypatch.setenv("EXODUS_LOGGER_OTHER", "Foo.Bar.Baz WARNING")
    monkeypatch.setenv("EXODUS_LOGGER_INVALID", "something-bad")

    cfg = EnvironmentLambdaConfig()
    logdict = cfg.logging_config
    assert logdict["loggers"] == {
        # All the valid vars should have made it into the log config dict.
        "Foo.Bar.Baz": {"level": "WARNING"},
        "foo bar": {"level": "INFO"},
        # There is also this default which is always included.
        "default": {"level": "WARNING"},
    }

    # The bad env var should have caused a log.
    assert (
        "Ignoring invalid logger env var: exodus_logger_invalid = something-bad"
        in caplog.text
    )
