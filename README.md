exodus-lambda
=============

AWS Lambda functions for Red Hat's Content Delivery Network

[![Build Status](https://github.com/release-engineering/exodus-lambda/actions/workflows/ci.yml/badge.svg?branch=master)
[![Coverage Status](https://coveralls.io/repos/github/release-engineering/exodus-lambda/badge.svg?branch=master)](https://coveralls.io/github/release-engineering/exodus-lambda?branch=master)

- [Source](https://github.com/release-engineering/exodus-lambda)
- [Documentation](https://release-engineering.github.io/exodus-lambda/)


Development
-----------

Patches may be contributed via pull requests to
https://github.com/release-engineering/exodus-lambda.

All changes must pass the automated test suite, along with various static
checks.

The [Black](https://black.readthedocs.io/) code style is enforced.
Enabling autoformatting via a pre-commit hook is recommended:

```
pip install -r requirements-dev.txt
pre-commit install
```


License
-------

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
