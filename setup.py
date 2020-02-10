from setuptools import setup, find_packages


def get_description():
    return "AWS Lambda functions for Red Hat's Content Delivery Network"


def get_long_description():
    with open("README.md") as f:
        text = f.read()

    # Long description is everything after README's initial heading
    idx = text.find("\n\n")
    return text[idx:]


def get_requirements():
    with open("requirements.txt") as f:
        return f.read().splitlines()


setup(
    name="cdn_lambda",
    version="0.1.0",
    packages=find_packages(exclude=["tests"]),
    package_data={},
    url="https://github.com/release-engineering/cdn-lambda",
    license="GNU General Public License",
    description=get_description(),
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    install_requires=get_requirements(),
    python_requires=">=3",
    project_urls={
        "Documentation": "https://release-engineering.github.io/cdn-lambda",
        "Changelog": "https://github.com/release-engineering/cdn-lambda/blob/master/CHANGELOG.md",
    },
)
