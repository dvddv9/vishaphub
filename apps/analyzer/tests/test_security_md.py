# -*- coding: utf-8 -*-
"""Doc-guard tests for SECURITY.md (P2-10).

Purpose: prevent regressions in the formal threat model
(deletion of sections, broken references).
"""
import re
from pathlib import Path


SECURITY_MD = Path("SECURITY.md")
TESTS_DIR = Path("tests")


def test_security_md_exists():
    assert SECURITY_MD.exists(), "SECURITY.md not found"
    assert SECURITY_MD.stat().st_size > 1000, "SECURITY.md too small"


def test_security_md_has_threat_models():
    content = SECURITY_MD.read_text(encoding="utf-8")
    assert "## Threat Model" in content, "Missing '## Threat Model'"
    assert "## Formal Threat Model (P2-10)" in content, "Missing formal section"


def test_security_md_has_formal_sections():
    content = SECURITY_MD.read_text(encoding="utf-8")
    required = [
        "### 1. Scope",
        "### 2. Assets",
        "### 3. Trust boundaries",
        "### 4. Abuse Cases & Controls (STRIDE)",
        "### 5. Verification",
        "### 6. Compliance Readiness",
        "### 7. Known Limitations (formal)",
    ]
    for section in required:
        assert section in content, f"Missing section: {section!r}"


def test_security_md_has_abuse_cases():
    content = SECURITY_MD.read_text(encoding="utf-8")
    abuse_ids = re.findall(r"AC-\d+", content)
    assert len(abuse_ids) >= 10, f"Expected >=10 abuse cases, got {len(abuse_ids)}"


def test_security_md_references_existing_tests():
    content = SECURITY_MD.read_text(encoding="utf-8")
    # find all "tests/test_*.py" references
    refs = set(re.findall(r"tests/test_[\w_]+\.py", content))
    assert refs, "No test references found in SECURITY.md"
    missing = [ref for ref in refs if not (Path(ref)).exists()]
    assert not missing, f"Referenced tests missing: {missing}"
