import functools
import json
import os
import time
import urllib
from datetime import datetime, timedelta, timezone

import boto3
import cachetools

from .base import LambdaBase
from .signer import Signer

CONF_FILE = os.environ.get("EXODUS_LAMBDA_CONF_FILE") or "lambda_config.json"

# Endpoint for AWS services.
# Normally, should be None.
# You might want to try e.g. "https://localhost:3377" if you want to test
# this code against localstack.
ENDPOINT_URL = os.environ.get("EXODUS_AWS_ENDPOINT_URL") or None


class OriginRequest(LambdaBase):
    def __init__(self, conf_file=CONF_FILE):
        super().__init__("origin-request", conf_file)
        self._db_client = None
        self._sm_client = None
        self._cache = cachetools.TTLCache(
            maxsize=1,
            ttl=timedelta(
                minutes=self.conf.get("config_cache_ttl", 2)
            ).total_seconds(),
            timer=time.monotonic,
        )
        self.handler = self.__wrap_version_check(self.handler)

    @property
    def db_client(self):
        if not self._db_client:
            self._db_client = boto3.client(
                "dynamodb",
                region_name=self.region,
                endpoint_url=ENDPOINT_URL,
            )

        return self._db_client

    @property
    def sm_client(self):
        if not self._sm_client:
            self._sm_client = boto3.client(
                "secretsmanager",
                region_name=self.region,
                endpoint_url=ENDPOINT_URL,
            )

        return self._sm_client

    @property
    def definitions(self):
        out = self._cache.get("exodus-config")
        if out is None:
            table = self.conf["config_table"]["name"]

            query_result = self.db_client.query(
                TableName=table,
                Limit=1,
                ScanIndexForward=False,
                KeyConditionExpression="config_id = :id and from_date <= :d",
                ExpressionAttributeValues={
                    ":id": {"S": "exodus-config"},
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
                item = query_result["Items"][0]
                out = json.loads(item["config"]["S"])
            else:
                # Provide dict with expected keys when no config is found.
                out = {
                    "origin_alias": [],
                    "rhui_alias": [],
                    "releasever_alias": [],
                    "listing": {},
                }

            self._cache["exodus-config"] = out

        return out

    @property
    def secret(self):
        out = self._cache.get("secret")
        if out is None:
            try:
                arn = self.conf["secret_arn"]
                self.logger.info("Attempting to get secret %s", arn)

                response = self.sm_client.get_secret_value(SecretId=arn)
                # get_secret_value response syntax:
                #  {
                #    "ARN": "string",
                #    "Name": "string",
                #    "VersionId": "string",
                #    "SecretBinary": b"bytes",
                #    "SecretString": "string",
                #    "VersionStages": [
                #        "string",
                #    ],
                #    "CreatedDate": datetime(2015, 1, 1)
                #  }
                #
                # We're interested in SecretString and expect it to be a JSON string
                # containing cookie_key.
                out = json.loads(response["SecretString"])
                self._cache["secret"] = out
                self.logger.info("Loaded and cached secret %s", arn)
            except Exception as exc_info:
                self.logger.error(
                    "Couldn't load secret %s", arn, exc_info=exc_info
                )
                raise exc_info

        return out

    @property
    def cookie_key(self):
        return self.secret["cookie_key"]

    def uri_alias(self, uri, aliases):
        # Resolve every alias between paths within the uri (e.g.
        # allow RHUI paths to be aliased to non-RHUI).
        #
        # Aliases are expected to come from cdn-definitions.

        remaining = aliases

        # We do multiple passes here to ensure that nested aliases
        # are resolved correctly, regardless of the order in which
        # they're provided.
        while remaining:
            processed = []

            for alias in remaining:
                if uri.startswith(alias["src"] + "/") or uri == alias["src"]:
                    uri = uri.replace(alias["src"], alias["dest"], 1)
                    processed.append(alias)

            if not processed:
                # We didn't resolve any alias, then we're done processing.
                break

            # We resolved at least one alias, so we need another round
            # in case others apply now. But take out anything we've already
            # processed, so it is not possible to recurse.
            remaining = [r for r in remaining if r not in processed]

        return uri

    def resolve_aliases(self, uri):
        # aliases relating to origin, e.g. content/origin <=> origin
        uri = self.uri_alias(uri, self.definitions.get("origin_alias"))

        # aliases relating to rhui; listing files are a special exemption
        # because they must be allowed to differ for rhui vs non-rhui.
        if not uri.endswith("/listing"):
            uri = self.uri_alias(uri, self.definitions.get("rhui_alias"))

        # aliases relating to releasever; e.g. /content/dist/rhel8/8 <=> /content/dist/rhel8/8.5
        uri = self.uri_alias(uri, self.definitions.get("releasever_alias"))

        return uri

    def handle_cookie_request(self, event):
        now = datetime.utcnow()
        ttl = timedelta(minutes=self.conf.get("cookie_ttl", 720))
        domain = event["Records"][0]["cf"]["config"]["distributionDomainName"]
        uri = event["Records"][0]["cf"]["request"]["uri"]

        self.logger.info("Handling cookie request: %s", uri)

        signer = Signer(self.cookie_key, self.conf.get("key_id"))
        cookies_content = signer.cookies_for_policy(
            append="; Secure; Path=/content/; Max-Age=%s"
            % int(ttl.total_seconds()),
            resource="https://%s/content/*" % domain,
            date_less_than=now + ttl,
        )
        cookies_origin = signer.cookies_for_policy(
            append="; Secure; Path=/origin/; Max-Age=%s"
            % int(ttl.total_seconds()),
            resource="https://%s/origin/*" % domain,
            date_less_than=now + ttl,
        )

        return {
            "status": "302",
            "headers": {
                "location": [
                    {"value": uri[len("/_/cookie") :]},
                ],
                "cache-control": [
                    {"value": "no-store"},
                ],
                "set-cookie": [
                    {"value": x} for x in (cookies_content + cookies_origin)
                ],
            },
        }

    def handle_listing_request(self, uri):
        if uri.endswith("/listing"):
            self.logger.info("Handling listing request: %s", uri)
            listing_data = self.definitions.get("listing")
            if listing_data:
                target = uri[: -len("/listing")]
                listing = listing_data.get(target)
                if listing:
                    return {
                        "body": "\n".join(listing["values"]) + "\n",
                        "status": "200",
                        "statusDescription": "OK",
                        "headers": {
                            "content-type": [
                                {"key": "Content-Type", "value": "text/plain"}
                            ]
                        },
                    }
                self.logger.info("No listing found for '%s'", uri)
            else:
                self.logger.info("No listing data defined")

        return {}

    def __wrap_version_check(self, handler):
        # Decorator wrapping every request to add x-exodus-version on responses
        # which generated directly without going to origin-response.

        @functools.wraps(handler)
        def new_handler(event, context):
            request = event["Records"][0]["cf"]["request"]
            response = handler(event, context)

            if "status" in response and "x-exodus-query" in (
                request.get("headers") or {}
            ):
                self.set_lambda_version(response)

            return response

        return new_handler

    def response_from_db(self, request, table, uri):
        self.logger.info("Querying '%s' table for '%s'...", table, uri)

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

        if not query_result["Items"]:
            return

        self.logger.info("Item found for '%s'", uri)

        try:
            # Validate If the item's "object_key" is "absent"
            object_key = query_result["Items"][0]["object_key"]["S"]
            if object_key == "absent":
                self.logger.info("Item absent for '%s'", uri)
                return {"status": "404", "statusDescription": "Not Found"}

            # Add custom header containing the original request uri
            request["headers"]["exodus-original-uri"] = [
                {"key": "exodus-original-uri", "value": request["uri"]}
            ]

            # Update request uri to point to S3 object key
            request["uri"] = "/" + object_key
            content_type = (
                query_result["Items"][0].get("content_type", {}).get("S")
            )
            if not content_type:
                # return "application/octet-stream" when content_type is empty
                content_type = "application/octet-stream"

            request["querystring"] = urllib.parse.urlencode(
                {"response-content-type": content_type}
            )

            self.logger.info(
                "The request value for origin_request end is '%s'",
                json.dumps(request, indent=4, sort_keys=True),
            )

            return request
        except Exception as err:
            self.logger.exception(
                "Exception occurred while processing %s",
                json.dumps(query_result["Items"][0]),
            )

            raise err

    def handler(self, event, context):
        # pylint: disable=unused-argument

        request = event["Records"][0]["cf"]["request"]

        if request["uri"].startswith("/_/cookie/"):
            return self.handle_cookie_request(event)

        uri = self.resolve_aliases(request["uri"])

        listing_response = self.handle_listing_request(uri)
        if listing_response:
            self.set_cache_control(uri, listing_response)
            return listing_response

        self.logger.info(
            "The request value for origin_request beginning is '%s'",
            json.dumps(request, indent=4, sort_keys=True),
        )
        self.logger.info(
            "The uri value for origin_request beginning is '%s'", uri
        )
        table = self.conf["table"]["name"]

        # Do not permit clients to explicitly request an index file
        if not uri.endswith("/" + self.index):
            index_uri = uri
            while index_uri.endswith("/"):
                index_uri = index_uri[:-1]
            index_uri = index_uri + "/" + self.index
            for query_uri in (uri, index_uri):
                if out := self.response_from_db(request, table, query_uri):
                    return out
        self.logger.info("No item found for '%s'", uri)
        return {"status": "404", "statusDescription": "Not Found"}


# Make handler available at module level
lambda_handler = OriginRequest().handler  # pylint: disable=invalid-name
