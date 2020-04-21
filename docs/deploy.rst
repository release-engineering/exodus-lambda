Deployment
==========


CDN Storage (Bucket & Table)
----------------------------

Each environment (dev, stage, prod, etc.) requires an `Amazon S3`_ bucket and a
`Amazon DynamoDB`_ table, as illustrated in :ref:`arch_ref`.

An `AWS CloudFormation`_ template is available to create these bucket-table
pairs, exodus-storage.yaml, run by the `AWS CLI`_ command
``aws cloudformation deploy``.

- Parameters
    - env
        The environment in which to deploy functions.
        Available values: dev (default), stage, prod

Additionally, an `Origin Access Identity`_ is created for use with
`Amazon CloudFront`_ distributions.

**Note**: The AWS region in which these resources are created is defined by
local configuration or environment variables. See: `AWS Config`_.

| **Example**:
| $ export AWS_DEFAULT_REGION=us-east-1
| $ aws cloudformation deploy ``\``
|   --template-file configuration/exodus-storage.yaml ``\``
|   --stack-name ... ``\``
|   --capabilities ... ``\``
|   --parameter-overrides env=...

Lambda Deployment Pipelines
---------------------------

In order for the CDN to work as designed, `Lambda@Edge`_ functions must be
deployed to handle requests to and responses from the CDN. To automate the
deployment of these functions, we use `AWS CodePipeline`_ pipelines. The
pipelines retrieve the source code, build the deployment package, and publish
it to `Lambda@Edge`_.

An `AWS CloudFormation`_ template is available to create these pipelines,
exodus-pipeline.yaml, run by the `AWS CLI`_ command
``aws cloudformation deploy``.

- Parameters
    - env
        The environment in which to deploy functions.
        Available values: dev (default), stage, prod
    - oai
        The origin access identity ID associated with the environment,
        created alongside the environment's bucket-table pair.
    - githubToken
        A GitHub access token for repository authentication
    - region
        The region in which resources are established.
        Should align with the environment's bucket-table pair.
    - email
        The email address to which notifications are sent.

| **Example**:
| $ export AWS_DEFAULT_REGION=us-east-1
| $ aws cloudformation deploy ``\``
|   --template-file configuration/exodus-pipeline.yaml ``\``
|   --stack-name ... ``\``
|   --capabilities ... ``\``
|   --parameter-overrides ``\``
|       env=... oai=... githubToken=... region=... email=...

Lambda Functions
----------------

The `Lambda@Edge`_ functions defined in this repository are intended to be
deployed by `AWS CodePipeline`_ pipelines, triggered by pushes to designated
git branch(es). However, the `AWS CloudFormation`_ template for function
deployment, exodus-lambda-deploy.yaml, can be run by the `AWS CLI`_ command
``aws cloudformation deploy`` once packaged.

- Parameters
    - env
        The environment in which to deploy functions.
        Available values: dev (default), stage, prod
    - oai
        The origin access identity ID associated with the environment,
        created alongside the environment's bucket-table pair.

| **Example**:
| $ export AWS_DEFAULT_REGION=us-east-1
| $ ./scripts/build-package
| $ aws cloudformation deploy ``\``
|   --template-file configuration/exodus-lambda-pkg.yaml ``\``
|   --stack-name ... ``\``
|   --capabilities ... ``\``
|   --parameter-overrides env=... oai=...

.. _Amazon S3: https://aws.amazon.com/s3/

.. _Amazon DynamoDB: https://aws.amazon.com/dynamodb/

.. _AWS CloudFormation: https://aws.amazon.com/cloudformation/

.. _AWS CLI: https://aws.amazon.com/cli/

.. _Origin Access Identity: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html

.. _Amazon CloudFront: https://aws.amazon.com/cloudfront/

.. _AWS Config: https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html

.. _Lambda@Edge: https://aws.amazon.com/lambda/edge/

.. _AWS CodePipeline: https://aws.amazon.com/codepipeline/
