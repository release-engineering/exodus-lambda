Tests
=====


Integration Test
----------------


The integration test is already integrated to `AWS CodePipeline`_ pipelines.


Test data prepare
~~~~~~~~~~~~~~~~

In order to support automated validation/integration tests against the exodus CDN, we need to create a set of reference testdata which can be deployed and used in each environment.

The test data prepare script located in the ``support/reftest/`` directory.
The ``support/reftest/reftest`` is used to prepare the test data, and the ``support/reftest/data.yml`` is used to specify the data which will be used.

The integration test use real testdata (real RHEL RPMs) but don't check them into the ``exodus-lambda`` repo. Instead, the script ``support/reftest/reftest`` support fetching the RPMs from production CDN for test data. Then, create DB items in `Amazon DynamoDB`_ and push the fetched data to `Amazon S3`_.

.. code-block:: none

    $ ./reftest prepare --table ... --bucket ... --cert ... --key ... --cacert ...

- Parameters
    - table:
        The AWS DynamoDB table name.
    - bucket:
        The AWS S3 bucket name.
    - cert:
        The client certificate file and password.
    - key:
        The private key file name.
    - cacert:
        The CA certificate to verify peer against.

.. note::
    If there are testdata paths which have unstable content and no stable alternatives, then the checksum field is not needed in ``data.yml`` and the checksum-verify step will be skipped.


Running the test locally 
~~~~~~~~~~~~~~~~~~~~~~~~~


The test code is located in the ``tests/integration/`` directory.
The test ``tests/integration/test_exodus.py`` covers all major implemented behaviors from exodus CDN.

- origin path alias
- rhui path alias
- Digest/Want-Digest
- Cache-Control
- Content-Type

.. code-block:: none

    # specify the CloudFormation stack for lambdafunction creation
    $ export STACK_NAME=...
    $ tox -e integration-tests

    # or you can directly use pytest and specify the CDN url
    $ pytest tests/integration/ --cdn-test-url ...


.. _Amazon S3: https://aws.amazon.com/s3/

.. _Amazon DynamoDB: https://aws.amazon.com/dynamodb/

.. _AWS CodePipeline: https://aws.amazon.com/codepipeline/
