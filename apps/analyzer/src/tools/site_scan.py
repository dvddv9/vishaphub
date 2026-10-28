"""Site checks: what a running deployment tells the world before anyone logs in.

This is deliberately shallow and polite. It answers «what does the site leak or omit»,
not «can I break it»: a handful of GET requests, a short timeout, and no exploitation
attempts. Anything deeper belongs to an authorised test, not to a demo.

Every check names the header, path or behaviour it looked at, so a finding can be
argued with — and every probe is bounded, because a scanner that hammers a site is a
problem, not a service.
"""
from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests

TIMEOUT = 10
MAX_REDIRECTS = 3
USER_AGENT = "VishapSiteCheck/1.0 (+https://github.com/dvddv9/vishaphub)"

#: Headers that cost nothing and prevent a class of attacks. Missing ones are findings.
EXPECTED_HEADERS = {
    "strict-transport-security": ("high", "HSTS is absent: a first visit can be downgraded to http"),
    "content-security-policy": ("medium", "CSP is absent: any injected script runs with full rights"),
    "x-content-type-options": ("medium", "X-Content-Type-Options is absent: browsers may sniff away the declared type"),
    "x-frame-options": ("medium", "X-Frame-Options is absent and no frame-ancestors is set: the site can be framed"),
    "referrer-policy": ("low", "Referrer-Policy is absent: full URLs leak to third parties"),
}

#: Files that should never be reachable. A 200 here is a leak, not a misconfiguration.
SENSITIVE_PATHS = {
    "/.git/config": "high",
    "/.env": "high",
    "/.env.local": "high",
    "/backup.zip": "medium",
    "/server-status": "medium",
    "/swagger.json": "low",
    "/api/swagger.json": "low",
    "/.DS_Store": "low",
}


@dataclass
class SiteFinding:
    rule: str
    severity: str
    message: str
    location: str = ""

    def as_dict(self) -> dict:
        return {"rule": self.rule, "severity": self.severity, "message": self.message, "location": self.location}


@dataclass
class SiteReport:
    url: str
    findings: list[SiteFinding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    checked: int = 0

    @property
    def verdict(self) -> str:
        if not self.findings:
            return "SAFE"
        if any(f.severity == "critical" for f in self.findings):
            return "EMERGENCY"
        return "REQUIRES_REVIEW"

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "verdict": self.verdict,
            "checked": self.checked,
            "findings": [f.as_dict() for f in self.findings],
            "notes": self.notes,
        }

    def to_markdown(self) -> str:
        lines = [f"# Site check: {self.url}", "",
                 f"**Verdict:** {self.verdict} · **requests:** {self.checked} · **findings:** {len(self.findings)}"]
        if self.findings:
            lines += ["", "| Severity | Rule | Finding | Where |", "|---|---|---|---|"]
            for f in self.findings:
                lines.append(f"| {f.severity} | {f.rule} | {f.message} | {f.location} |")
        else:
            lines += ["", "No findings."]
        if self.notes:
            lines += ["", "## Notes", *[f"- {n}" for n in self.notes]]
        return "\n".join(lines)


def _normalise(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise ValueError("url is required")
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("only http and https are supported")
    if not parsed.netloc:
        raise ValueError("url has no host")
    return text


def _certificate_days(host: str) -> int | None:
    """Days until the certificate expires, or None when it cannot be read."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, 443), timeout=TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
    except (OSError, ssl.SSLError, ValueError):
        return None
    if not cert or "notAfter" not in cert:
        return None
    from datetime import datetime, timezone
    expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    return max(0, (expires - datetime.now(timezone.utc)).days)


def scan(url: str, session: requests.Session | None = None) -> SiteReport:
    """Check one site. Bounded: a few requests, a short timeout, no exploitation."""
    target = _normalise(url)
    report = SiteReport(url=target)
    http = session or requests.Session()
    http.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})

    if target.startswith("http://"):
        report.findings.append(SiteFinding(
            "https-missing", "high", "the site answers over plain http", target))

    try:
        response = http.get(target, timeout=TIMEOUT, allow_redirects=True)
        report.checked += 1
    except requests.RequestException as exc:
        report.notes.append(f"could not reach the site: {type(exc).__name__}: {exc}")
        return report

    final = response.url
    if final.startswith("http://"):
        report.findings.append(SiteFinding(
            "https-not-enforced", "high", "the final URL is plain http after redirects", final))

    headers = {k.lower(): v for k, v in response.headers.items()}

    for name, (severity, message) in EXPECTED_HEADERS.items():
        if name == "x-frame-options" and "frame-ancestors" in headers.get("content-security-policy", "").lower():
            continue
        if name not in headers:
            report.findings.append(SiteFinding("header-missing", severity, message, name))

    if headers.get("server"):
        report.notes.append(f"server header: {headers['server']}")
    if headers.get("x-powered-by"):
        report.findings.append(SiteFinding(
            "version-disclosure", "low", "the stack is advertised in X-Powered-By",
            headers["x-powered-by"]))

    cors = headers.get("access-control-allow-origin", "")
    if cors.strip() == "*" and headers.get("access-control-allow-credentials", "").lower() == "true":
        report.findings.append(SiteFinding(
            "cors-wildcard", "high", "CORS allows any origin together with credentials", final))

    for cookie in response.cookies:
        name = cookie.name
        if not cookie.secure:
            report.findings.append(SiteFinding(
                "cookie-not-secure", "medium", f"cookie {name} can travel over http", name))
        has_httponly = any(name in str(v) and "HttpOnly" in str(v) for v in [response.headers.get("set-cookie", "")])
        if not has_httponly:
            report.findings.append(SiteFinding(
                "cookie-no-httponly", "low", f"cookie {name} is readable from JavaScript", name))

    parsed = urlparse(final)
    if parsed.hostname:
        days = _certificate_days(parsed.hostname)
        if days is not None:
            report.notes.append(f"certificate expires in {days} days")
            if days < 14:
                report.findings.append(SiteFinding(
                    "certificate-expiring", "high", f"the certificate expires in {days} days", parsed.hostname))

    for path, severity in SENSITIVE_PATHS.items():
        probe = urljoin(final, path)
        try:
            head = http.get(probe, timeout=TIMEOUT, allow_redirects=False, stream=True)
            report.checked += 1
            status = head.status_code
            head.close()
        except requests.RequestException:
            continue
        if status == 200:
            report.findings.append(SiteFinding(
                "exposed-path", severity, f"{path} is served with 200", probe))

    return report


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="vishap site", description="Check a deployed site: headers, cookies, exposed paths, certificate.")
    parser.add_argument("url", help="site URL")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    args = parser.parse_args(argv)

    report = scan(args.url)
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.to_markdown())
    return 0 if report.verdict == "SAFE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
