# Patch check (no model)

`vishap-hub patch-check --snapshot DIR --diff fix.diff --spec spec.json [--json]` and
`patchcheck.check(snapshot, diff=... | files=..., spec=...)`. The same snapshot and the same diff give the
same result; a model is never asked.

## What a patch is

A bounded unified diff against a known snapshot (the model's whole-file patch is turned into the same
diff, so there is one path and one set of limits). It is applied to a copy in memory; the snapshot is never
modified. Refused as `FIX_REJECTED`, with the reason:

- more than 20 files, more than 2000 changed lines, a diff over 200 000 bytes;
- a path that is absolute, has a drive letter or climbs out (`..`);
- a path that belongs to the trusted checks: any `test_*.py` / `*_test.py`, anything the spec lists as a
  test, `conftest.py`, `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`, `noxfile.py`,
  `sitecustomize.py`, `.coveragerc`, `.github/`, `.git/`;
- a hunk that does not match the snapshot, a file that is not in it, a file that already exists, a rename;
- a patched Python file that does not parse.

## How the status is decided

1. The analyser's rules run on the snapshot and on the patched copy. Findings are compared per file and rule.
2. The validator runs on the patched copy, through the confirmed isolation only (a worker container, or a
   network namespace). No confirmed isolation, or the validator cannot run: `FIX_UNVERIFIED`. Nothing ran.
3. A check that fails after the patch and passed before: `FIX_REJECTED`. The validator's verdict alone is not
   trusted: a failing test leaves it at NEEDS_REVIEW. A check that already failed before proves nothing about
   the fix and keeps the result at `FIX_PARTIAL`.
4. New findings: `FIX_REJECTED`.
5. A trusted exploit test hook (`exploit(before, after)`): an exploit that still works after the patch is
   `FIX_REJECTED`; one that never reproduced on the original cannot verify.

`FIX_VERIFIED` needs all of: applied cleanly, no trusted path touched, the rules found fewer findings and no
new one, no critical or high finding left, the deliverable's own tests ran and passed in a confirmed isolation,
and nothing went away with the patch. Otherwise `FIX_PARTIAL`, naming what is missing.

What cannot buy a verification: deleting the file or function that held the finding (code went away),
deleting or editing a test (trusted), a patch whose tests never ran, a finding that merely disappeared.

The fix status complements the risk verdict and never changes it.