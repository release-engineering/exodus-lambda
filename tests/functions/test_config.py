from exodus_lambda.functions.config import EnvironmentLambdaConfig

# Tests for config classes.
#
# The classes are near 100% covered by other tests. Only edge cases
# not reached elsewhere are covered here.


def test_default_region():
    cfg = EnvironmentLambdaConfig()
    assert cfg.item_table_regions == ["us-east-1"]
