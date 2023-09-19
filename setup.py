from setuptools import find_packages, setup


def get_description():
    return "AWS Lambda functions for Red Hat's Content Delivery Network"


def get_long_description():
    with open("README.md") as readme:
        text = readme.read()

    # Long description is everything after README's initial heading
    idx = text.find("\n\n")
    return text[idx:]


def get_requirements():
    with open("requirements.in") as reqs:
        return [line.split()[0] for line in reqs.read().splitlines()]


setup(
    name="exodus-lambda",
    version="0.0.1",
    packages=find_packages(exclude=["tests"]),
    include_package_data=True,
    url="https://github.com/release-engineering/exodus-lambda",
    license="GNU General Public License",
    description=get_description(),
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
    ],
    install_requires=get_requirements(),
    python_requires=">=3.11",
    project_urls={
        "Documentation": "https://release-engineering.github.io/exodus-lambda"
    },
)
