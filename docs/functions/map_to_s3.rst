map_to_s3
=========

This function provides mapping from a web URI, delivered by an AWS CloudFront
event, to the key of an object in an AWS S3 bucket.

The mapping between the URI and the object key is defined by the provided AWS
DynamoDB table this function is deployed with.

Required schemas for the DynamoDB table and S3 bucket can be found in the
:doc:`schema reference <../schema-reference>`.

Deployment
----------

This function may be deployed like any other AWS Lambda function using the
following event and environment variables.

Event
^^^^^
The event for this function must be a CloudFront distribution origin-request to
an S3 bucket.

Environment Variables
^^^^^^^^^^^^^^^^^^^^^
- DB_TABLE_NAME
    (Required)

    The name of the DynamoDB table from which to derive mapping.
- DB_TABLE_REGION
    (Optional)

    The AWS region in which the table resides.
    If omitted, the region used is that of the function.

`AWS Lambda Environment Variables
<https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html>`_
