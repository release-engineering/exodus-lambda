import requests
import pytest


def test_exodus_basic(cdn_test_url):
    url = (
        cdn_test_url
        + "/content/aus/rhel/server/6/6.5/x86_64/os/Packages/c/cpio-2.10-12.el6_5.x86_64.rpm"
    )

    r = requests.get(url)
    assert r.status_code == 200
    assert "cache-control" not in r.headers


def test_header_not_exist_file(cdn_test_url):
    url = (
        cdn_test_url
        + "/content/aus/rhel/server/6/6.5/x86_64/os/Packages/c/cpio-2.10-12.el6_5.x86_64.rpm_not_exist"
    )
    r = requests.get(url)
    assert r.status_code == 404
    assert "cache-control" not in r.headers


# Test data for exodus-lambda
# serving repo entry points with appropriate cache headers
testdata_cache_control_path = [
    "/content/dist/rhel/server/5/listing",
    "/content/dist/rhel/server/5/5.6/listing",
    "/content/dist/rhel/server/5/5.7/listing",
    "/content/dist/rhel/server/7/7.2/x86_64/rhev-mgmt-agent/3/os/repodata/repomd.xml",
    "/content/dist/rhel/atomic/7/7Server/x86_64/ostree/repo/refs/heads/rhel-atomic-host/7/x86_64/standard",
]


@pytest.mark.parametrize("testdata_path", testdata_cache_control_path)
def test_header_cache_control(cdn_test_url, testdata_path):
    url = cdn_test_url + testdata_path
    r = requests.get(url)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "max-age=600"


def test_header_want_digest_GET(cdn_test_url):
    headers = {"want-digest": "id-sha-256"}
    url = cdn_test_url + "/content/dist/rhel/server/5/5.7/listing"
    r = requests.get(url, headers=headers)
    assert r.status_code == 200
    assert (
        r.headers["digest"]
        == "id-sha-256=tR9N3Ab93snnOJJnHx8lMAzNQjX6eYr9Acr5ZEbcK/E="
    )


def test_header_want_digest_HEAD(cdn_test_url):
    headers = {"want-digest": "id-sha-256"}
    url = cdn_test_url + "/content/dist/rhel/server/5/5.7/listing"
    r = requests.head(url, headers=headers)
    assert r.status_code == 200
    assert (
        r.headers["digest"]
        == "id-sha-256=tR9N3Ab93snnOJJnHx8lMAzNQjX6eYr9Acr5ZEbcK/E="
    )


# Test data for exodus-lambda
# serving yum repodata with correct Content-Type
testdata_content_type_path = [
    "/content/dist/rhel/server/7/7.4/x86_64/os/repodata/fd23895d43f54a50bbd0509809dd5f45298bfd6b-other.sqlite.bz2",
    "/content/dist/rhel/server/7/7.4/x86_64/os/repodata/cb753af26534673064bd593500d747d7288d75b2-filelists.xml.gz",
    "/content/dist/rhel/server/7/7.2/x86_64/rhev-mgmt-agent/3/os/repodata/repomd.xml",
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


testdata_origin_alias_path = [
    "/origin/rpms/bash/4.4.19/8.el8_0/fd431d51/bash-4.4.19-8.el8_0.x86_64.rpm",
    "/origin/rpm/bash/4.4.19/8.el8_0/fd431d51/bash-4.4.19-8.el8_0.x86_64.rpm",
    "/content/origin/rpms/bash/4.4.19/8.el8_0/fd431d51/bash-4.4.19-8.el8_0.x86_64.rpm",
    "/content/origin/rpm/bash/4.4.19/8.el8_0/fd431d51/bash-4.4.19-8.el8_0.x86_64.rpm",
]


# use Want-Digest/Digest to check if alias take effect
@pytest.mark.parametrize("testdata_path", testdata_origin_alias_path)
def test_origin_path_alias(cdn_test_url, testdata_path):
    headers = {"want-digest": "id-sha-256"}
    url = cdn_test_url + testdata_path
    r = requests.head(url, headers=headers)
    assert r.status_code == 200
    assert (
        r.headers["digest"]
        == "id-sha-256=QWT/LAEW1mZXi6XkVqsDuIeI37QvuT/JGywdpwnYZoY="
    )


testdata_rhui_alias_path_aus = [
    "/content/aus/rhel/server/6/6.5/x86_64/os/Packages/c/cpio-2.10-12.el6_5.x86_64.rpm",
    "/content/aus/rhel/rhui/server/6/6.5/x86_64/os/Packages/c/cpio-2.10-12.el6_5.x86_64.rpm",
]


@pytest.mark.parametrize("testdata_path", testdata_rhui_alias_path_aus)
def test_rhui_path_alias_aus(cdn_test_url, testdata_path):
    headers = {"want-digest": "id-sha-256"}
    url = cdn_test_url + testdata_path
    r = requests.head(url, headers=headers)
    assert r.status_code == 200
    assert (
        r.headers["digest"]
        == "id-sha-256=BjFlOLkNOqsg9HhxMjB/bTMNqaSLqxGhPgphb89iLOU="
    )


testdata_rhui_alias_path_rhel8 = [
    "/content/dist/rhel8/8.1/x86_64/baseos/os/Packages/i/iptables-1.8.2-16.el8.x86_64.rpm",
    "/content/dist/rhel8/rhui/8.1/x86_64/baseos/os/Packages/i/iptables-1.8.2-16.el8.x86_64.rpm",
]


@pytest.mark.parametrize("testdata_path", testdata_rhui_alias_path_rhel8)
def test_rhui_path_alias_rhel8(cdn_test_url, testdata_path):
    headers = {"want-digest": "id-sha-256"}
    url = cdn_test_url + testdata_path
    r = requests.head(url, headers=headers)
    assert r.status_code == 200
    assert (
        r.headers["digest"]
        == "id-sha-256=WA2MMEwPzpikfPAoOEnl6ffo9ce9p2aSEkl2UEaUfkA="
    )
