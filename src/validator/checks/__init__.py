"""Deterministic checks. Each module exposes ``run(root, spec) -> CheckResult``.

Rules of this layer:

* no network, no LLM — a validator that needs a model to say "pass" is not a validator;
* read-only — the deliverable is never modified;
* one concern per module, so a failing check names the thing that broke.
"""
