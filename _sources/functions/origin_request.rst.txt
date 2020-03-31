origin_request
=========

The origin_request function provides mapping from a web URI, delivered by an AWS
CloudFront event, to the key of an object in an AWS S3 bucket.

Using this function, a URI like "/path/to/s3/file" would be transformed to
something like "/some-s3-file-object-key".

The mapping between the URI and the object key is defined by the AWS DynamoDB
table specified in the configuration file that this function is deployed with.

Required schemas for the DynamoDB table and S3 bucket can be found in the
:doc:`schema reference <../schema-reference>`.

Deployment
----------

This function may be deployed like any other AWS Lambda function using the
following event and configuration file.

Event
^^^^^
The event for this function must be a CloudFront distribution origin-request to
an S3 bucket.

Configuration
^^^^^^^^^^^^^
The origin_request function must be deployed with the lambda_config.json configuration
file.

- table
    The DynamoDB table from which to derive path to key mapping.

    - name
        The name of the DynamoDB table.
    - region
        The AWS region in which the table resides.
