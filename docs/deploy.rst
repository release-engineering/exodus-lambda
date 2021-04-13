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

.. _AWS CloudFormation: https://aws.amazon.com/cloudformation/

.. _AWS CLI: https://aws.amazon.com/cli/

.. _AWS CloudFront: https://aws.amazon.com/cloudfront/

.. _Lambda@Edge: https://aws.amazon.com/lambda/edge/

.. _AWS CodePipeline: https://aws.amazon.com/codepipeline/
