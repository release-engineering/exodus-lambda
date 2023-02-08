import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

from requests import Response

# Helpers for dealing with lambda inputs and outputs.


class LambdaInput:
    """Helper for generating input event(s) to a lambda."""

    def __init__(
        self,
        wsgi_environ: Dict[str, Any],
        request: Optional[Dict[str, Any]] = None,
        response: Optional[Response] = None,
    ):
        self._wsgi_environ = wsgi_environ
        self._request_id = str(uuid.uuid4())
        self._response = response
        self.request = request or self._new_request()

    def config(self, event_type: str):
        """Returns the config element of a cloudfront event."""
        return {
            "distributionDomainName": self._wsgi_environ["SERVER_NAME"],
            "distributionId": "FAKEFRONT",
            "eventType": event_type,
            "requestId": self._request_id,
        }

    def _new_request(self):
        headers = {}
        for key, value in self._wsgi_environ.items():
            # e.g. HTTP_USER_AGENT => user-agent
            if key.startswith("HTTP_"):
                key = key[len("HTTP_") :].lower()
                key = key.replace("_", "-")
                headers[key] = [
                    {
                        "key": key,
                        "value": value,
                    }
                ]

        return {
            "clientIp": self._wsgi_environ["REMOTE_ADDR"],
            "headers": headers,
            "method": self._wsgi_environ["REQUEST_METHOD"],
            "querystring": self._wsgi_environ["QUERY_STRING"],
            "uri": self._wsgi_environ["PATH_INFO"],
        }

    @property
    def response(self):
        """Returns the response element of a cloudfront event."""
        # not valid to call this if there's no response passed in.
        assert self._response

        headers = {}
        for key, val in self._response.headers.items():
            # TODO: should we actually copy all of the headers from
            # origin or should it be filtered somehow? Should investigate
            # and copy what cloudfront does.
            headers[key] = [{"key": key, "value": val}]

        return {
            "headers": headers,
            "status": str(self._response.status_code),
            "statusDescription": self._response.reason,
        }

    @property
    def origin_request(self):
        """Returns an origin-request event corresponding to this request."""
        cf = {
            "config": self.config("origin-request"),
            "request": self.request,
        }

        return {"Records": [{"cf": cf}]}

    @property
    def origin_response(self):
        """Returns an origin-response event corresponding to this request."""
        cf = {
            "config": self.config("origin-response"),
            "request": self.request,
            "response": self.response,
        }

        return {"Records": [{"cf": cf}]}


class LambdaOutput:
    """Helper for handling an output event from a lambda, possibly
    converting it to a WSGI response.
    """

    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw

    @property
    def status(self) -> Optional[str]:
        """Status code returned by lambda (possibly None)."""
        return self.raw.get("status")

    @property
    def wsgi_status(self) -> str:
        """Status string as appropriate for use in WSGI output."""
        assert self.status
        return f"{self.status} {self.raw.get('statusDescription', '')}"

    @property
    def wsgi_headers(self) -> List[Tuple[str, str]]:
        """Headers returned by lambda, in the structure used by WSGI."""
        out = []
        for headername, headerlist in (self.raw.get("headers") or {}).items():
            for h in headerlist:
                out.append((h.get("key", headername), h["value"]))

        return out

    @property
    def wsgi_body(self) -> Iterable[bytes]:
        if self.raw.get("body"):
            # FIXME: this would break if our lambda ever produces a
            # binary response. This never currently happens though.
            return [self.raw["body"].encode("utf-8")]
        return []

    @property
    def uri(self) -> str:
        return self.raw["uri"]

    @property
    def querystring(self) -> Optional[str]:
        return self.raw.get("querystring")

    @property
    def method(self) -> str:
        return self.raw["method"]
