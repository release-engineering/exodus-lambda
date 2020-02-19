map_to_s3 Schemas
=================

The following schemas are required of AWS S3 bucket objects and DynamoDB table
items for use with the map_to_s3 AWS Lambda function.

S3 Bucket Schema
----------------

Objects should be stored in the origin S3 bucket using the file’s sha256
checksum as their key.

DynamoDB Table Schema
---------------------

DynamoDB table items must possess the following keys and attributes.

Additional attributes are supported by the no-SQL model and may be used as
needed.

Keys
^^^^
- web_uri
    (Primary)

    A logical path to the desired content, excluding the hostname,
    i.e., "/content/place/somepic.png".

- from_date
    (Sort)

    The datetime at which the content is made available, i.e.,
    "2020-02-17T20:48:13.037+00:00".

    Only content sooner than or equal to the current date and time may be
    retrieved from the origin.

Attributes
^^^^^^^^^^
- object_key
    The key of the file object stored in the origin S3 bucket.