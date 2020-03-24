import json
import logging
from datetime import datetime, timezone

import boto3

LOG = logging.getLogger("map-to-s3-lambda")


class LambdaClient(object):
    def __init__(self, conf_file="map_to_s3.json"):
        self._conf_file = conf_file

        self._conf = None
        self._db_client = None

    @property
    def conf(self):
        if not self._conf:
            with open(self._conf_file, "r") as json_file:
                self._conf = json.load(json_file)

        return self._conf

    @property
    def db_client(self):
        if not self._db_client:
            self._db_client = boto3.client(
                "dynamodb", region_name=self.conf["table"]["region"]
            )

        return self._db_client

    def uri_alias(self, uri):
        # NOTE: Aliases are processed in the order they are listed
        for alias in self.conf["uri_aliases"]:
            if uri.startswith(alias[0]):
                uri = uri.replace(alias[0], alias[1])
        return uri

    def handler(self, event, context):
        # pylint: disable=unused-argument

        request = event["Records"][0]["cf"]["request"]
        uri = self.uri_alias(request["uri"])
        table = self.conf["table"]["name"]

        LOG.info("Querying '%s' table for '%s'...", table, uri)

        query_result = self.db_client.query(
            TableName=table,
            Limit=1,
            ScanIndexForward=False,
            KeyConditionExpression="web_uri = :u and from_date <= :d",
            ExpressionAttributeValues={
                ":u": {"S": uri},
                ":d": {
                    "S": str(
                        datetime.now(timezone.utc).isoformat(
                            timespec="milliseconds"
                        )
                    )
                },
            },
        )

        if query_result["Items"]:
            LOG.info("Item found for '%s'", uri)

            try:
                # Update request uri to point to S3 object key
                request["uri"] = (
                    "/" + query_result["Items"][0]["object_key"]["S"]
                )

                return request
            except Exception as err:
                LOG.exception(
                    "Exception occurred while processing %s",
                    json.dumps(query_result["Items"][0]),
                )

                raise err
        else:
            LOG.info("No item found for '%s'", uri)

            # Report 404 to prevent attempts on S3
            return {
                "status": "404",
                "statusDescription": "Not Found",
            }


# Make handler available at module level
lambda_handler = LambdaClient().handler  # pylint: disable=invalid-name
