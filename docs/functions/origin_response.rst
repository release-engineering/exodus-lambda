origin_response
===============

The origin_response function appends the following Cache-Control header to a
CloudFront distribution's HTTP response from the origin server for a defined
list of path patterns:

        [{"key": "Cache-Control", "value": "max-age=600",}]

Deployment
----------

This function may be deployed like any other AWS Lambda function using the
following event.

Event
^^^^^
The event for this function must be a CloudFront distribution origin-response.

Configuration
^^^^^^^^^^^^^
The CloudFront distribution must support caching based on request headers.
The custom 'cache-control' request header must be whitelisted.
