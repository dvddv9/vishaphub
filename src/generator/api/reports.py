"""Turn a pipeline result into the JSON the API returns."""

from __future__ import annotations


def report(res, log: list[str]) -> dict:
    out = res.to_dict()
    out["log"] = log
    if res.files and res.design:
        planned = {f.path for f in res.design.files}
        out["files"] = {p: c for p, c in res.files.items() if p in planned}
    if res.deliver:
        out["trace"] = res.deliver.trace
        out["diff"] = res.deliver.diff      # against an empty folder: the API never reads the disk
    return out


def http_status(out: dict) -> int:
    err = out.get("error") or ""
    if not err:
        return 200
    if err.startswith("spec:"):
        return 422          # the spec itself is wrong
    if err.startswith("build:"):
        return 502          # the model failed or answered unusably
    return 500
