Deployment
==========

Lambda Functions
----------------

The `Lambda@Edge`_ functions defined in this repository are intended to be
deployed by `AWS CodePipeline`_ pipelines, triggered by pushes to a designated
git branch(es). However, the `AWS CloudFormation`_ template for function
deployment, exodus-lambda-deploy.yaml, can be run by the `AWS CLI`_ command
``aws cloudformation deploy`` once packaged.

- Parameters
    - env
        The project name under which resources are created.
        Available values: dev, stage, prod
        Default: dev
    - oai
        An `AWS CloudFront`_ origin access identity.
    - project:
        The project name under which resources are created.
        Default: exodus
    - lambdafunctionrole:
        The IAM Role ARN for Lambda Function resource.

| **Example**:

.. code-block:: console

 $ export $PROJECT=...
 $ export $ENV_TYPE=...
 $ ./scripts/build-package
 $ aws cloudformation deploy \
        --template-file configuration/exodus-lambda-pkg.yaml \
        --stack-name ... \
        --capabilities ... \
        --parameter-overrides env=$ENV_TYPE project=$PROJECT \
            oai=... lambdafunctionrole=...


Environment Variables
---------------------

Lambdas should be configured using the following environment variables.
All variables not listed as "required" have reasonable defaults.

    ``EXODUS_TABLE`` *(required)*
        The name of a DynamoDB table containing URI/content mappings.

    ``EXODUS_CONFIG_TABLE`` *(required)*
        The name of a DynamoDB table containing volatile config influencing the
        lambdas, such as $releasever aliases. This config can be updated
        without a new deployment.

    ``EXODUS_SECRET_ARN`` *(required)*
        ARN identifying a secret from which a private key can be loaded for
        signing cookies.

    ``EXODUS_KEY_ID`` *(required)*
        ID of the keypair corresponding to the private key found in the above secret.

    ``EXODUS_TABLE_REGIONS``
        Comma-separated list of regions in which ``EXODUS_TABLE`` can be accessed
        (if it is configured as a global table).

    ``EXODUS_CONFIG_CACHE_TTL``
        How long, in minutes, to cache volatile config read from ``EXODUS_CONFIG_TABLE``.

    ``EXODUS_COOKIE_TTL``
        How long, in minutes, before signed cookies expire.

    ``EXODUS_HEADERS_MAX_AGE``
        How long, in seconds, before certain pieces of mutable content (such as repomd.xml)
        should be considered stale. Used to set ``Cache-Control: max-age`` on some responses.

    ``EXODUS_LAMBDA_VERSION``
        A version string uniquely identifying the currently deployed version of exodus-lambda,
        for debugging purposes.

    ``EXODUS_LOG_FORMAT``
        Format string for Python loggers.

    ``EXODUS_LOGGER_*``
        Should contain a value of the form ``<loggername> <level>``,
        such as ``origin-request DEBUG``.

        Sets the level of the specified logger.

        The environment variable's wildcard suffix allows for any number
        of loggers to be configured. The specific value used as a suffix
        has no effect.



.. _AWS CloudFormation: https://aws.amazon.com/cloudformation/

.. _AWS CLI: https://aws.amazon.com/cli/

.. _AWS CloudFront: https://aws.amazon.com/cloudfront/

.. _Lambda@Edge: https://aws.amazon.com/lambda/edge/

.. _AWS CodePipeline: https://aws.amazon.com/codepipeline/
