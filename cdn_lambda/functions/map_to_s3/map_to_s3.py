import json
import logging
from datetime import datetime, timezone

import boto3

LOG = logging.getLogger("map-to-s3-lambda")


def load_conf(conf_file):
    with open(conf_file, "r") as json_file:
        content = json.load(json_file)

    return content


def lambda_handler(event, context, conf_file=None):
    # pylint: disable=unused-argument

    conf_file = conf_file or "map_to_s3.json"
    conf = load_conf(conf_file)

    # Get uri from origin request event
    request = event["Records"][0]["cf"]["request"]
    web_uri = request["uri"]

    LOG.info("Querying '%s' table for '%s'...", conf["table"]["name"], web_uri)

    iso_now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

    db_client = boto3.client("dynamodb", region_name=conf["table"]["region"])
    query_result = db_client.query(
        TableName=conf["table"]["name"],
        Limit=1,
        ScanIndexForward=False,
        KeyConditionExpression="web_uri = :u and from_date <= :d",
        ExpressionAttributeValues={
            ":u": {"S": web_uri},
            ":d": {"S": str(iso_now)},
        },
    )

    if query_result["Items"]:
        LOG.info("Item found for '%s'", web_uri)

        try:
            # Update request uri to point to S3 object key
            request["uri"] = "/" + query_result["Items"][0]["object_key"]["S"]

            return request
        except Exception as err:
            LOG.exception(
                "Exception occurred while processing %s",
                json.dumps(query_result["Items"][0]),
            )

            raise err
    else:
        LOG.info("No item for '%s'", web_uri)

        # Report 404 to prevent attempts on S3
        return {
            "status": "404",
            "statusDescription": "Not Found",
        }
