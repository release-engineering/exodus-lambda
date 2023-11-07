import logging
from typing import Any, Optional

import boto3
import botocore

LOG = logging.getLogger("exodus_lambda")


class QueryHelper:
    """A helper to perform DynamoDB queries with failover between regions."""

    def __init__(self, conf: dict[str, Any], endpoint_url: Optional[str]):
        self._conf = conf
        self._endpoint_url = endpoint_url
        self._clients: dict[str, Any] = {}

    def _client(self, region: str):
        # Return client for particular region
        if region not in self._clients:
            boto_config = botocore.config.Config(
                region_name=region,
                connect_timeout=self._conf.get("connect_timeout"),
                read_timeout=self._conf.get("read_timeout"),
            )
            self._clients[region] = boto3.client(
                "dynamodb",
                endpoint_url=self._endpoint_url,
                config=boto_config,
            )

        return self._clients[region]

    def _regions(self, table_name: str) -> list[str]:
        # Return all AWS region(s) to be used for a specific table
        out = None
        for conf_key in ("table", "config_table"):
            table_conf = self._conf.get(conf_key) or {}
            if table_conf.get("name") == table_name:
                out = table_conf.get("available_regions")
                break

        if not out:
            LOG.warning(
                "No config for %s, applying default regions", table_name
            )
            out = ["us-east-1"]

        return out

    def query(self, TableName: str, **kwargs) -> dict[str, Any]:
        """Query items from a table.

        This method has the same API as:
        https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb/client/query.html#DynamoDB.Client.query

        ...but it will issue the query across *all* configured regions
        for that table, in the order listed, until no error occurs.
        """
        output_error: Optional[BaseException] = None

        for region in self._regions(TableName):
            client = self._client(region)

            # Should we fail over only in case of error or also in case of
            # missing items?
            #
            # We choose "only in case of error" because:
            #
            # - if failing over in case of missing items, every 404 needs
            #   to query every region
            #
            # - there is no known disaster scenario under which an item
            #   would be missing from the primary but available from a
            #   secondary. If items are accidentally deleted from the primary,
            #   that would be expected to propagate to the secondaries within
            #   a few seconds, so failover wouldn't help much.
            #

            try:
                out = client.query(TableName=TableName, **kwargs)
                if output_error:
                    LOG.warning(
                        (
                            "Failover: query for table %s succeeded in region "
                            "%s after prior errors"
                        ),
                        TableName,
                        region,
                    )
                return out
            except (
                Exception  # pylint: disable=broad-exception-caught
            ) as error:
                LOG.warning(
                    "Error querying table %s in region %s",
                    TableName,
                    region,
                    exc_info=True,
                )
                # Chain exceptions across multiple regions so no error details
                # are lost
                error.__cause__ = output_error
                output_error = error

        # If we get here, every region failed.
        assert output_error
        raise output_error
