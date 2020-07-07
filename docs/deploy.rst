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
    - env:
        The environment in which to deploy functions.
        Available values: dev, stage, prod
        Default: dev
    - project:
        The project name under which the resources are created.
        Default: exodus
    - oai:
        The origin access identity ID associated with the environment.

**Note**: The AWS region in which these resources are created is defined by
local configuration or environment variables. See: `AWS Config`_.

| **Example**:

.. code-block:: console

 $ aws cloudformation deploy \
        --template-file configuration/exodus-storage.yaml \
        --stack-name ... \
        --capabilities ... \
        --parameter-overrides env=... project=... oai=...

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
    - env:
        The project name under which resources are created.
        Available values: dev, stage, prod
        Default: dev
    - oai:
        The origin access identity ID associated with the environment,
        created alongside the environment's bucket-table pair.
    - repoOwner:
        The parent of the targeted repository.
        Default: release-engineering
    - repoName:
        The targeted repository.
        Default: exodus-lambda
    - repoBranch:
        The source branch of the targeted repository.
        Default: master (if env=dev), deploy (if env=stage)
    - githubToken:
        A GitHub access token for repository authentication.
    - region:
        The region in which resources are established.
        Should align with the environment's bucket-table pair.
        Default: us-east-1
    - email:
        The email address to which notifications are sent.
        Default: project-exodus@redhat.com
    - project:
        The project name under which resources are created.
        Default: exodus
    - useCloudTrail:
        Determines whether to create CloudTrail resources.
        Available values: true, false
        Default: false
    - cloudformationrole:
        The IAM Role ARN for CloudFormation resource.
    - codepipelinerole:
        The IAM Role ARN for CodePipeline resource.
    - cloudwatcheventrole:
        The IAM Role ARN for CloudWatch resource.
    - lambdafunctionrole:
        The IAM Role ARN for Lambda Function resource.

| **Example**:

.. code-block:: console

 $ aws cloudformation deploy \
        --template-file configuration/exodus-pipeline-resources.yaml \
        --stack-name ... --capabilities ... \
        --parameter-overrides project=... region=... useCloudTrail=... codebuildrole=...

 $ aws cloudformation deploy \
        --template-file configuration/exodus-pipeline.yaml \
        --stack-name ... \
        --capabilities ... \
        --parameter-overrides env=...  project=... \
            repoOwner=... repoName=... repoBranch=... \
            githubToken=... region=... email=... oai=...\
            cloudformationrole=... codepipelinerole=... \
            cloudwatcheventrole=... lambdafunctionrole=...


Lambda Functions
----------------

The `Lambda@Edge`_ functions defined in this repository are intended to be
deployed by `AWS CodePipeline`_ pipelines, triggered by pushes to designated
git branch(es). However, the `AWS CloudFormation`_ template for function
deployment, exodus-lambda-deploy.yaml, can be run by the `AWS CLI`_ command
``aws cloudformation deploy`` once packaged.

- Parameters
    - env
        The project name under which resources are created.
        Available values: dev, stage, prod
        Default: dev
    - oai
        The origin access identity ID associated with the environment,
        created alongside the environment's bucket-table pair.
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

.. _Amazon S3: https://aws.amazon.com/s3/

.. _Amazon DynamoDB: https://aws.amazon.com/dynamodb/

.. _AWS CloudFormation: https://aws.amazon.com/cloudformation/

.. _AWS CLI: https://aws.amazon.com/cli/

.. _AWS Config: https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html

.. _Lambda@Edge: https://aws.amazon.com/lambda/edge/

.. _AWS CodePipeline: https://aws.amazon.com/codepipeline/
