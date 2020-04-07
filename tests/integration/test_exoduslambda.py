import pytest
import logging
import requests

from .utils import get_config, get_db_client
from boto3.dynamodb.conditions import Key, Attr


class TestExodus:
    def setup(self):
        self.config = get_config()
        self.db_client = get_db_client()

    def test_cache_headers(self):
        table = self.db_client.Table(self.config["dynamodb_table"])
        for pattern in self.config["patterns"]:
            # TODO: update "contains" ComparisonOperator to match real condition
            response = table.scan(
                FilterExpression=Attr("web_uri").contains(pattern)
            )

            # Concatenate URI matching the pattern
            uri = self.config["cloudfront"] + response["Items"][0]["web_uri"]
            r = requests.get(uri)

            assert r.status_code == 200
            assert r.headers["cache-control"] == "max-age=600"

    def test_no_cache_headers(self):
        r = requests.get(self.config["cloudfront"] + "/no_exist_file")

        assert r.status_code == 404
        assert "cache-control" not in r.headers
