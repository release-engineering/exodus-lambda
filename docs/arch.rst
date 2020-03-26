Architecture
============


Overview
--------

This diagram shows the relationship between all major components used
in the delivery of content via the CDN.

.. graphviz:: arch.gv

- Numbered connections represent the sequence of events when the CDN processes a request.
- For clarity, SHA256 checksums have been truncated (as in ``8e7750e50734f...``). In reality,
  the system stores complete checksums.
- The CloudFront CDN shown in the above diagram may itself be hosted behind another CDN,
  so client requests may pass through additional layers not expressed here.


Components
----------

client
    A client requesting data from the CDN.

    This could be ``dnf``, ``yum``, Satellite, ``curl``, a web browser, etc.

CloudFront CDN
    The `Amazon CloudFront`_ content delivery network.

controller
    An abstract component representing the built-in behaviors of CloudFront,
    such as:

    - basic HTTP request handling
    - serving responses from cache
    - invoking Lambda functions
    - delegating requests to S3

    ...and so on.

DynamoDB
    `Amazon DynamoDB`_ NoSQL database service.

    The CDN uses a single DynamoDB table which primarily contains mappings
    between URIs and S3 object keys.

    For more information about the data contained here, see :ref:`schema_ref`.

S3
    `Amazon S3`_, Simple Storage Service.

    The CDN uses S3 to store the binary objects retrievable by clients.
    A single bucket is used, configured as the origin of the CloudFront CDN.

    One object corresponds to one file which can be downloaded from the CDN;
    this includes files considered to be content (such as RPMs) and files considered
    to be metadata (such as yum repo metadata files).

    Each object's key is its own SHA256 checksum, ensuring that content accessible
    via many paths on the CDN need only be stored once.

    S3 metadata is used in some cases to customize the response behavior of each object;
    for example, metadata is used to adjust ``Content-Type`` headers in responses.
    Publishing tools are responsible for setting this metadata accurately.

    For more information about the data contained here, see :ref:`schema_ref`.

cdn-lambda
    A project including Python-based implementations of `Lambda@Edge`_ functions for the CDN.

    You are currently reading the documentation of this project.

origin_request
    A `Lambda@Edge`_ function connected to "origin request" events in CloudFront.

    This function is primarily responsible for translating the path given in the client's
    request into an S3 object key via a DynamoDB query.  Assuming the client has requested
    existing content, this Lambda function will rewrite the request's URI into a valid S3
    object key before returning the request to the controller.  The function itself does
    not request data from S3, nor generate a response directly.

    For more information about this function's behavior, see :ref:`function_ref`.

origin_response
    A `Lambda@Edge`_ function connected to "origin response" events in CloudFront.

    This function is primarily responsible for tweaking certain response headers
    before allowing CloudFront to serve the response to clients.  For example,
    caching behavior is influenced by setting a Cache-Control header for certain
    responses.

    For more information about this function's behavior, see :ref:`function_ref`.

publishing tools
    Represents the tools used by Red Hat to publish content onto the CDN.

    These tools insert data into the CDN's S3 and DynamoDB services in order to publish
    content.

    A further explanation of these tools is out of scope for this document; it suffices
    to know that the tools are designed with an awareness of the CDN architecture
    described here.

.. _Lambda@Edge: https://aws.amazon.com/lambda/edge/

.. _Amazon CloudFront: https://aws.amazon.com/cloudfront/

.. _Amazon DynamoDB: https://aws.amazon.com/dynamodb/

.. _Amazon S3: https://aws.amazon.com/s3/
