import requests
import pytest


def test_exodus_basic(cdn_test_url):
    url = (
        cdn_test_url
        + "/content/beta/rhel8/8/x86_64/exodus_test/os/bash-4.4.19-7.el8.x86_64.rpm"
    )

    r = requests.get(url)
    assert r.status_code == 200
    assert "cache-control" not in r.headers


def test_header_not_exist_file(cdn_test_url):
    url = (
        cdn_test_url
        + "/content/beta/rhel8/8/x86_64/exodus_test/os/bash-4.4.19-7.el8.x86_64.rpm_no"
    )
    r = requests.get(url)
    assert r.status_code == 404
    assert "cache-control" not in r.headers


# Test data for exodus-lambda
# serving repo entry points with appropriate cache headers
testdata_cache_control_path = [
    "/content/beta/rhel8/8/x86_64/exodus_test/os/listing",
    "/content/beta/rhel8/8/x86_64/exodus_test_ctype/os/repodata/repomd.xml",
    "/content/beta/rhel8/8/x86_64/exodus_test/os/ostree/repo/refs/heads/sub_dir/testing",
]


@pytest.mark.parametrize("testdata_path", testdata_cache_control_path)
def test_header_cache_control(cdn_test_url, testdata_path):
    url = cdn_test_url + testdata_path
    r = requests.get(url)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "max-age=600"


def test_header_want_digest_GET(cdn_test_url):
    headers = {"want-digest": "id-sha-256"}
    url = cdn_test_url + "/content/beta/rhel8/8/x86_64/exodus_test/os/listing"
    r = requests.get(url, headers=headers)
    assert r.status_code == 200
    assert (
        r.headers["digest"]
        == "id-sha-256=jbuWD7I1f2C3IcJT6acQqIz1kI/pffRTD3krSieXQQc="
    )


def test_header_want_digest_HEAD(cdn_test_url):
    headers = {"want-digest": "id-sha-256"}
    url = cdn_test_url + "/content/beta/rhel8/8/x86_64/exodus_test/os/listing"
    r = requests.head(url, headers=headers)
    assert r.status_code == 200
    assert (
        r.headers["digest"]
        == "id-sha-256=jbuWD7I1f2C3IcJT6acQqIz1kI/pffRTD3krSieXQQc="
    )


# Test data for exodus-lambda
# serving yum repodata with correct Content-Type
testdata_content_type_path = [
    "/content/beta/rhel8/8/x86_64/exodus_test_ctype_2/os/repodata/acc399cea3af512ef5f773604f0ca7c129c6a973c6364786954ec49e88f3582f-filelists.sqlite.bz2",
    "/content/beta/rhel8/8/x86_64/exodus_test_ctype_2/os/repodata/47e27d9fff2396c32b4a6c1462282fdb5c8330a14c8ae647e39242cf5c5281ce-primary.xml.gz",
    "/origin/files/sha256/5c/5c50cbb468bf0bde6587019e5ba51346506793a65e914d06c6f98b4c9c0a1598/repomd.xml",
]


def assert_content_type(url, content_type):
    if url.endswith("repomd.xml"):
        assert content_type == "application/xml"
    elif url.endswith(".gz"):
        assert content_type == "application/x-gzip"
    elif url.endswith(".bz2"):
        assert content_type == "application/x-bzip"
    else:
        raise ValueError("invalid test data format")


@pytest.mark.parametrize("testdata_path", testdata_content_type_path)
def test_content_type_header_GET(cdn_test_url, testdata_path):
    url = cdn_test_url + testdata_path
    r = requests.get(url)
    assert r.status_code == 200
    assert_content_type(url, r.headers["content-type"])


@pytest.mark.parametrize("testdata_path", testdata_content_type_path)
def test_content_type_header_HEAD(cdn_test_url, testdata_path):
    url = cdn_test_url + testdata_path
    r = requests.head(url)
    assert r.status_code == 200
    assert_content_type(url, r.headers["content-type"])
