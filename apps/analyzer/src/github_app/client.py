# -*- coding: utf-8 -*-
"""GitHub App API client for bounded pull-request repository scans."""
import io
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from src.github_app.auth import generate_jwt

GITHUB_API = "https://api.github.com"
MAX_ARCHIVE_BYTES = 50_000_000
MAX_SOURCE_FILES = 2_000
MAX_SOURCE_FILE_BYTES = 400_000


def _headers(token: str, accept: str = "application/vnd.github+json") -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": accept}


def get_installation_token(installation_id: int) -> str:
    """Exchange the App JWT for an installation access token."""
    jwt_token = generate_jwt()
    r = httpx.post(
        f"{GITHUB_API}/app/installations/{installation_id}/access_tokens",
        headers=_headers(jwt_token),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["token"]


def post_pr_comment(repo: str, pr_number: int, body: str, token: str) -> dict:
    """Create or update the single Vishap summary comment on a pull request."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments"
    headers = _headers(token)
    r = httpx.get(url, headers=headers, params={"per_page": 100}, timeout=15)
    r.raise_for_status()
    marker = "<!-- vishap-security -->"
    old = next((item for item in r.json() if marker in str(item.get("body") or "")), None)
    payload = {"body": f"{marker}\n{body}"}
    if old:
        r = httpx.patch(f"{url}/{old['id']}", headers=headers, json=payload, timeout=15)
    else:
        r = httpx.post(url, headers=headers, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def post_commit_status(repo: str, sha: str, state: str, description: str, token: str,
                       target_url: str = "") -> dict:
    """Set the status context branch protection can require to block a merge."""
    body = {"state": state, "context": "vishap/security", "description": description[:140]}
    if target_url:
        body["target_url"] = target_url
    r = httpx.post(f"{GITHUB_API}/repos/{repo}/statuses/{sha}", headers=_headers(token),
                   json=body, timeout=15)
    r.raise_for_status()
    return r.json()


def _is_scannable(name: str) -> bool:
    from src.tools.repo_scan import _is_code_file
    return _is_code_file(name)


def _extract_snapshot(archive: bytes, root: Path) -> int:
    """Safely materialize only bounded source files from a GitHub ZIP archive."""
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise ValueError("GitHub source archive exceeds the configured size limit")
    count = 0
    total = 0
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        for info in sorted(zipped.infolist(), key=lambda item: item.filename):
            if info.is_dir() or count >= MAX_SOURCE_FILES or info.file_size > MAX_SOURCE_FILE_BYTES:
                continue
            parts = PurePosixPath(info.filename).parts
            if len(parts) < 2 or any(part in ("..", "") for part in parts) or PurePosixPath(info.filename).is_absolute():
                continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                continue
            rel_parts = parts[1:]  # strip GitHub's generated archive directory
            if not rel_parts or not _is_scannable(rel_parts[-1]):
                continue
            total += info.file_size
            if total > MAX_ARCHIVE_BYTES:
                break
            content = zipped.read(info)
            target = (root / Path(*rel_parts)).resolve()
            if not target.is_relative_to(root.resolve()):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            count += 1
    return count


def analyze_pr_diff(repo: str, pr_number: int, token: str, head_sha: str = "") -> dict:
    """Scan changed PR lines using a bounded full-source snapshot for import context."""
    headers = _headers(token)
    pr = httpx.get(f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}", headers=headers, timeout=20)
    pr.raise_for_status()
    sha = head_sha or (pr.json().get("head") or {}).get("sha")
    if not sha:
        raise ValueError("GitHub pull request response has no head commit SHA")
    diff_response = httpx.get(f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
                              headers=_headers(token, accept="application/vnd.github.v3.diff"), timeout=30)
    diff_response.raise_for_status()
    if len(diff_response.content) > 5_000_000:
        raise ValueError("pull request diff exceeds the 5 MB analysis limit")
    with httpx.stream("GET", f"{GITHUB_API}/repos/{repo}/zipball/{sha}", headers=headers,
                      timeout=60, follow_redirects=True) as response:
        response.raise_for_status()
        archive = bytearray()
        for part in response.iter_bytes():
            archive.extend(part)
            if len(archive) > MAX_ARCHIVE_BYTES:
                raise ValueError("GitHub source archive exceeds the 50 MB analysis limit")

    from src.tools.repo_scan import scan_diff

    with tempfile.TemporaryDirectory(prefix="vishap-pr-") as directory:
        root = Path(directory)
        files = _extract_snapshot(bytes(archive), root)
        if not files:
            raise ValueError("the pull request snapshot contained no supported source files")
        result = scan_diff(str(root), diff_response.text, max_files=MAX_SOURCE_FILES,
                           max_file_bytes=MAX_SOURCE_FILE_BYTES)

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    fail_on = os.getenv("VISHAP_GITHUB_FAIL_ON", "high").strip().lower()
    if fail_on not in order:
        fail_on = "high"
    threshold = order[fail_on]
    blocking = [f for f in result["findings"] if order.get(str(f.get("severity", "low")).lower(), 9) <= threshold]
    verdict = ("EMERGENCY" if any(f.get("severity") == "critical" for f in blocking) else
               "FAIL" if blocking else "REQUIRES_REVIEW" if result["findings"] else "SAFE")
    return {"verdict": verdict, "findings": result["findings"], "files_scanned": files,
            "gate": {"context": "vishap/security", "fail_on": fail_on, "failed": bool(blocking),
                     "blocking_findings": len(blocking)}, "summary": result}
