"""Site checks: the report must be bounded, honest and never a pretend audit."""
import pytest

from src.tools import site_scan


class FakeResponse:
    def __init__(self, url="https://example.test/", status=200, headers=None, cookies=None):
        self.url = url
        self.status_code = status
        self.headers = headers or {}
        self.cookies = cookies or []
        self.closed = False

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, page, probes=None):
        self.page = page
        self.probes = probes or {}
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None, allow_redirects=True, stream=False):
        self.calls.append(url)
        for path, response in self.probes.items():
            if url.endswith(path):
                return response
        for path in site_scan.SENSITIVE_PATHS:
            if url.endswith(path):
                # a probe path the test did not stage is absent, as on a real site
                return FakeResponse(url=url, status=404, headers={})
        return self.page


GOOD_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


def test_url_without_a_scheme_is_assumed_https():
    assert site_scan._normalise("example.test") == "https://example.test"


@pytest.mark.parametrize("bad", ["", "ftp://example.test", "https://"])
def test_bad_urls_are_refused(bad):
    with pytest.raises(ValueError):
        site_scan._normalise(bad)


def test_missing_headers_are_reported():
    session = FakeSession(FakeResponse(headers={}))
    report = site_scan.scan("https://example.test", session=session)
    rules = {f.rule for f in report.findings}
    assert "header-missing" in rules
    assert report.verdict == "REQUIRES_REVIEW"


def test_present_headers_are_not_reported():
    session = FakeSession(FakeResponse(headers=GOOD_HEADERS))
    report = site_scan.scan("https://example.test", session=session)
    header_findings = [f for f in report.findings if f.rule == "header-missing"]
    assert header_findings == []
    assert report.verdict == "SAFE"


def test_frame_ancestors_replaces_x_frame_options():
    headers = dict(GOOD_HEADERS)
    headers.pop("X-Frame-Options")
    headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    session = FakeSession(FakeResponse(headers=headers))
    report = site_scan.scan("https://example.test", session=session)
    assert not any("X-Frame-Options" in f.message for f in report.findings)


def test_plain_http_is_a_finding():
    session = FakeSession(FakeResponse(url="http://example.test/", headers=GOOD_HEADERS))
    report = site_scan.scan("http://example.test", session=session)
    assert any(f.rule == "https-missing" for f in report.findings)


def test_cors_wildcard_with_credentials_is_high():
    headers = dict(GOOD_HEADERS)
    headers["Access-Control-Allow-Origin"] = "*"
    headers["Access-Control-Allow-Credentials"] = "true"
    session = FakeSession(FakeResponse(headers=headers))
    report = site_scan.scan("https://example.test", session=session)
    cors = [f for f in report.findings if f.rule == "cors-wildcard"]
    assert cors and cors[0].severity == "high"


def test_exposed_env_is_reported():
    page = FakeResponse(headers=GOOD_HEADERS)
    probes = {"/.env": FakeResponse(url="https://example.test/.env", status=200)}
    report = site_scan.scan("https://example.test", session=FakeSession(page, probes))
    exposed = [f for f in report.findings if f.rule == "exposed-path"]
    assert any(f.location.endswith("/.env") for f in exposed)


def test_probe_count_is_bounded():
    page = FakeResponse(headers=GOOD_HEADERS)
    session = FakeSession(page)
    report = site_scan.scan("https://example.test", session=session)
    # one page + the sensitive paths, and nothing else
    assert report.checked <= 1 + len(site_scan.SENSITIVE_PATHS)


def test_unreachable_site_is_a_note_not_a_crash():
    class Boom(FakeSession):
        def get(self, *a, **k):
            import requests
            raise requests.RequestException("no route to host")

    report = site_scan.scan("https://example.test", session=Boom(FakeResponse()))
    assert report.findings == []
    assert any("could not reach" in note for note in report.notes)
