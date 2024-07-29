import binascii
import functools
import gzip
import json
import os
import time
from base64 import b64decode
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlencode

import cachetools

from .base import LambdaBase
from .db import QueryHelper

CONF_FILE = os.environ.get("EXODUS_LAMBDA_CONF_FILE") or "lambda_config.json"

# Endpoint for AWS services.
# Normally, should be None.
# You might want to try e.g. "https://localhost:3377" if you want to test
# this code against localstack.
ENDPOINT_URL = os.environ.get("EXODUS_AWS_ENDPOINT_URL") or None


def cf_b64decode(data):
    return b64decode(
        data.replace("-", "+").replace("_", "=").replace("~", "/")
    )


class OriginRequest(LambdaBase):
    def __init__(self, conf_file=CONF_FILE):
        super().__init__("origin-request", conf_file)
        self._sm_client = None
        self._cache = cachetools.TTLCache(
            maxsize=1,
            ttl=timedelta(
                minutes=self.conf.get("config_cache_ttl", 2)
            ).total_seconds(),
            timer=time.monotonic,
        )
        self._db = QueryHelper(self.conf, ENDPOINT_URL)
        self.handler = self.__wrap_version_check(self.handler)

    @property
    def definitions(self):
        out = self._cache.get("exodus-config")
        if out is None:
            table = self.conf["config_table"]["name"]

            query_result = self._db.query(
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
                if item_encoded := item["config"].get("B"):
                    # new-style: config is compressed and stored as bytes
                    item_bytes = b64decode(item_encoded)
                    item_json = gzip.decompress(item_bytes).decode()
                else:
                    # old-style, config was stored as JSON string.
                    # Consider deleting this code path in 2025
                    item_json = item["config"]["S"]
                out = json.loads(item_json)
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

        self.logger.debug("Resolved request URI: %s", uri)

        return uri

    def handle_cookie_request(self, event):
        request = event["Records"][0]["cf"]["request"]
        uri = request["uri"]
        params = {k: v[0] for k, v in parse_qs(request["querystring"]).items()}

        try:
            set_cookies = json.loads(
                cf_b64decode(params["CloudFront-Cookies"])
            )
        except (
            KeyError,
            binascii.Error,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            self.logger.debug(
                "Unable to load cookies from redirect request: %s",
                request,
                exc_info=exc,
            )
            return {"status": "400", "statusDescription": "Bad Request"}

        self.logger.info("Handling cookie request: %s", uri)

        response = {
            "status": "302",
            "headers": {
                "location": [
                    {"value": uri[len("/_/cookie") :]},
                ],
                "cache-control": [
                    {"value": "no-store"},
                ],
                "set-cookie": [{"value": x} for x in set_cookies],
            },
        }
        self.logger.debug(
            "Generated cookie request response", extra={"response": response}
        )
        return response

    def handle_listing_request(self, uri):
        if uri.endswith("/listing"):
            self.logger.info("Handling listing request: %s", uri)
            listing_data = self.definitions.get("listing")
            if listing_data:
                target = uri[: -len("/listing")]
                listing = listing_data.get(target)
                if listing:
                    response = {
                        "body": "\n".join(listing["values"]) + "\n",
                        "status": "200",
                        "statusDescription": "OK",
                        "headers": {
                            "content-type": [
                                {"key": "Content-Type", "value": "text/plain"}
                            ]
                        },
                    }
                    self.logger.debug(
                        "Generated listing request response",
                        extra={"response": response},
                    )
                    return response
                self.logger.info("No listing found for URI: %s", uri)
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

        query_result = self._db.query(
            TableName=table,
            Limit=1,
            ConsistentRead=True,
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

        self.logger.info("Item found for URI: %s", uri)

        try:
            # Validate If the item's "object_key" is "absent"
            object_key = query_result["Items"][0]["object_key"]["S"]
            if object_key == "absent":
                self.logger.info("Item absent for URI: %s", uri)
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

            request["querystring"] = urlencode(
                {"response-content-type": content_type}
            )

            self.logger.debug(
                "Updated request value for origin_request",
                extra={"request": request},
            )

            return request
        except Exception as err:
            self.logger.exception(
                "Exception occurred while processing item: %s",
                query_result["Items"][0],
            )

            raise err

    def validate_request(self, request):
        # Validate URI and query string lengths, as those are only elements provided by users.
        #
        # For request structure example, see
        # https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/lambda-event-structure.html#example-origin-request

        valid = True

        if not 0 < len(request["uri"]) < 2000:
            self.logger.error("uri exceeds length limits: %s", request["uri"])
            valid = False
        if "querystring" in request and not len(request["querystring"]) < 4000:
            self.logger.error(
                "querystring exceeds length limits: %s", request["querystring"]
            )
            valid = False
        return valid

    def handler(self, event, context):
        # pylint: disable=unused-argument

        request = event["Records"][0]["cf"]["request"]

        if not self.validate_request(request):
            return {"status": "400", "statusDescription": "Bad Request"}

        self.logger.debug(
            "Incoming request value for origin_request",
            extra={"request": request},
        )

        request["uri"] = unquote(request["uri"])
        original_uri = request["uri"]

        if request["uri"].startswith("/_/cookie/"):
            return self.handle_cookie_request(event)

        uri = self.resolve_aliases(request["uri"])

        listing_response = self.handle_listing_request(uri)
        if listing_response:
            self.set_cache_control(uri, listing_response)
            return listing_response

        table = self.conf["table"]["name"]

        # Do not permit clients to explicitly request an index file
        if not uri.endswith("/" + self.index):
            index_uri = uri
            while index_uri.endswith("/"):
                index_uri = index_uri[:-1]
            index_uri = index_uri + "/" + self.index
            for query_uri in (uri, index_uri):
                if out := self.response_from_db(request, table, query_uri):
                    if query_uri == index_uri and not uri.endswith("/"):
                        # If we got an index response but the user's requested uri doesn't
                        # end in '/', then we can't directly serve the index.
                        # We need to instead serve a redirect back to the same path with
                        # '/' appended.
                        #
                        # This is due to the way HTML links are resolved, for example:
                        #
                        #   current URL  |  link href  |  resolved URL
                        # ---------------+-------------+---------------------------
                        #   /some/repo   |  Packages/  | /some/Packages (bad)
                        #   /some/repo/  |  Packages/  | /some/repo/Packages (good)
                        #
                        # This is conceptually similar to:
                        # https://httpd.apache.org/docs/2.4/mod/mod_dir.html#directoryslash
                        self.logger.debug(
                            "Sending '/' redirect for index at %s", uri
                        )

                        response = {
                            "status": "302",
                            "headers": {
                                "location": [
                                    {"value": original_uri + "/"},
                                ],
                            },
                        }
                        self.logger.debug(
                            "Generated redirect response",
                            extra={"response": response},
                        )
                        return response

                    return out
        self.logger.info("No item found for URI: %s", uri)
        return {"status": "404", "statusDescription": "Not Found"}


# Make handler available at module level
lambda_handler = OriginRequest().handler  # pylint: disable=invalid-name
