"""Run several specs, one output folder each.

The analog of Vishap's `pipeline/batch.py`. `run_batch` takes spec files, runs the five stages for each in a
small thread pool, and returns one row per spec. Each spec writes to `<out_root>/<spec name>/`, so two runs never
touch the same files; the history file is the only shared thing and it is written under a lock
(storage/history.py). A spec that already has a finished run with the same hash is skipped unless `again`.

One failing spec never stops the others.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from generator.observability.logging import get_logger
from generator.pipeline.orchestrator import run_pipeline
from generator.storage.history import find_done_by_hash
from generator.tools.spec import SpecError, load_spec

MAX_WORKERS = 8
SPEC_SUFFIXES = (".yaml", ".yml")


@dataclass
class BatchRow:
    spec: str
    out: str
    status: str = ""          # done | blocked | error | skipped
    exit_code: int = 0
    verdict: str = ""
    run_id: str = ""
    error: str = ""
    usage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def find_specs(paths: list[str | Path]) -> list[Path]:
    """Spec files named on the command line; a folder contributes its *.yaml / *.yml files."""
    found: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found += sorted(f for f in p.iterdir() if f.suffix.lower() in SPEC_SUFFIXES and f.is_file())
        else:
            found.append(p)
    seen, unique = set(), []
    for f in found:
        key = str(f.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def out_name(spec: Path, taken: set[str]) -> str:
    """A folder name for a spec: its file stem, made safe, and unique within the batch."""
    base = re.sub(r"[^A-Za-z0-9_.-]+", "-", spec.stem).strip(".-") or "spec"
    name, n = base, 2
    while name in taken:
        name, n = f"{base}-{n}", n + 1
    taken.add(name)
    return name


def _one(spec: Path, out: Path, again: bool, kw: dict) -> BatchRow:
    row = BatchRow(spec=str(spec), out=str(out))
    try:
        sha = load_spec(spec).sha256
    except (SpecError, OSError) as e:
        row.status, row.exit_code, row.error = "error", 2, f"spec: {e}"
        return row
    if not again:
        done = find_done_by_hash(out, sha)
        if done:
            row.status, row.verdict, row.run_id = "skipped", done.get("verdict", ""), done.get("run_id", "")
            return row
    try:
        res = run_pipeline(spec, out_dir=out, **kw)
    except Exception as e:      # a bug in one run must not stop the batch
        get_logger("batch").exception("run failed: %s", spec)
        row.status, row.exit_code, row.error = "error", 2, f"{type(e).__name__}: {e}"
        return row
    row.exit_code, row.error, row.usage = res.exit_code, res.error, res.usage
    row.verdict = res.verify.code_verdict if res.verify else ""
    row.run_id = res.deliver.run_id if res.deliver and res.deliver.written else ""
    row.status = "error" if res.exit_code == 2 else "blocked" if res.exit_code == 1 else "done"
    return row


def run_batch(specs: list[Path], out_root: str | Path, *, workers: int = 2, again: bool = False,
              on_row: Callable[[BatchRow], None] = lambda row: None, **pipeline_kw) -> list[BatchRow]:
    """Rows in the order of `specs`. `on_row` is called as each finishes (from a worker thread)."""
    root = Path(out_root)
    taken: set[str] = set()
    jobs = [(spec, root / out_name(spec, taken)) for spec in specs]
    workers = max(1, min(workers, MAX_WORKERS, len(jobs) or 1))
    rows: list[BatchRow | None] = [None] * len(jobs)

    def work(i: int) -> None:
        spec, out = jobs[i]
        rows[i] = _one(spec, out, again, pipeline_kw)
        on_row(rows[i])

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vg-batch") as pool:
        list(pool.map(work, range(len(jobs))))
    return [r for r in rows if r is not None]


def batch_exit_code(rows: list[BatchRow]) -> int:
    """2 when any run errored, else 1 when any was blocked, else 0."""
    if any(r.status == "error" for r in rows):
        return 2
    return 1 if any(r.status == "blocked" for r in rows) else 0
