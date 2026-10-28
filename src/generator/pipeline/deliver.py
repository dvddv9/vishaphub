"""Deliver: gate, diff, backup, write, trace, rollback.

Rules:
- Files are written only inside the output root. Every target is
  resolved and checked, symlinks are refused, a failure half way undoes
  what this run already wrote.
- Without `gate` the files are written and problems stay in the report.
  With `gate` a blocked run writes nothing; `force` writes anyway and the
  trace says `forced: true`.
- Every run leaves a manifest and backups under `.vishap/runs/<id>/`,
  so `rollback` can put back the old files and remove the new ones. A
  rollback refuses when a file changed since the run (unless `force`).
"""

from __future__ import annotations

import datetime as dt
import difflib
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from generator.pipeline.build import BuildCheck
from generator.pipeline.design import DesignResult
from generator.pipeline.intake import Requirement
from generator.tools.spec import Spec
from generator.pipeline.verdict import VerifyResult
from generator.tools.quality_gate import Gate, GateResult, evaluate_gate

META_DIR = ".vishap"


class DeliverError(RuntimeError):
    pass


# ---------------------------------------------------------------- helpers

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _target(root: Path, rel: str) -> Path:
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts or "\\" in rel or (len(rel) > 1 and rel[1] == ":"):
        raise DeliverError(f"path is not allowed: {rel}")
    target = root.joinpath(*p.parts)
    node = target
    while node != root:
        if node.is_symlink():
            raise DeliverError(f"refusing to write through a symlink: {rel}")
        node = node.parent
        if root not in node.parents and node != root:
            raise DeliverError(f"path leaves the output folder: {rel}")
    if target.exists() and not target.is_file():
        raise DeliverError(f"not a regular file: {rel}")
    return target


def _write_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".vg-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content.encode("utf-8"))
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _read(target: Path) -> str | None:
    return target.read_text(encoding="utf-8", errors="replace") if target.exists() else None


# ---------------------------------------------------------------- trace

def build_trace(spec: Spec, requirements: tuple[Requirement, ...], design: DesignResult,
                build: BuildCheck, verify: VerifyResult, *, run_id: str, now: dt.datetime,
                forced: bool, gate: GateResult, gated: bool) -> dict:
    tests_in = {f.path: list(f.tests_found) for f in build.files}
    verdict_of = {v.id: v for v in verify.requirements}
    rows = []
    for r in requirements:
        v = verdict_of[r.id]
        files = [f.path for f in design.files if r.id in f.requirements and f.role == "code"]
        tests = sorted({e.name for e in v.evidence if e.source == "model-test"})
        rows.append({
            "id": r.id, "text": r.text, "priority": r.priority,
            "source": {"field": r.source.field, "line": r.source.line},
            "code": files, "tests": tests, "status": v.status, "note": v.note,
            "evidence": [e.to_dict() for e in v.evidence],
        })
    return {
        "run": {"id": run_id, "time": now.isoformat(timespec="seconds"), "forced": forced,
                "gated": gated},
        "forced": forced,
        "spec": {"path": spec.path.name if hasattr(spec.path, "name") else str(spec.path),
                 "sha256": spec.sha256, "version": spec.version,
                 "updated": spec.updated.isoformat(),
                 "stale": verify.spec_stale, "age_days": verify.spec_age_days},
        "verdict": verify.code_verdict,
        "gate": gate.to_dict(),
        "coverage": verify.to_dict()["coverage"],
        "analyzer": verify.analyzer.to_dict() if verify.analyzer else None,
        "gaps": [g.to_dict() for g in design.gaps],
        "problems": list(verify.problems),
        "notes": list(verify.notes),
        "files": {},
        "tests_in_files": tests_in,
        "requirements": rows,
    }


# ---------------------------------------------------------------- deliver

@dataclass(frozen=True)
class FileAction:
    path: str
    action: str         # created | overwritten | unchanged

    def to_dict(self) -> dict:
        return {"path": self.path, "action": self.action}


@dataclass(frozen=True)
class DeliverResult:
    run_id: str
    written: bool
    blocked: bool
    forced: bool
    dry_run: bool
    gate: GateResult
    actions: tuple[FileAction, ...]
    diff: str
    trace: dict
    trace_path: str
    rollback_hint: str

    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "written": self.written, "blocked": self.blocked,
                "forced": self.forced, "dry_run": self.dry_run, "gate": self.gate.to_dict(),
                "actions": [a.to_dict() for a in self.actions], "trace_path": self.trace_path,
                "rollback": self.rollback_hint}


def _diff(rel: str, old: str | None, new: str) -> str:
    a = (old or "").splitlines(keepends=True)
    b = new.splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        a, b, fromfile=f"a/{rel}" if old is not None else "/dev/null", tofile=f"b/{rel}"))


def deliver(*, spec: Spec, requirements: tuple[Requirement, ...], design: DesignResult,
            files: dict[str, str], build: BuildCheck, verify: VerifyResult,
            out_root: str | os.PathLike, gate: bool = False, force: bool = False,
            dry_run: bool = False, quality_gate: Gate | None = None,
            now: dt.datetime | None = None, provenance: dict | None = None,
            extra: dict | None = None) -> DeliverResult:
    now = now or dt.datetime.now().replace(microsecond=0)
    root = Path(out_root).resolve()
    if root.exists() and not root.is_dir():
        raise DeliverError(f"output folder is a file: {root}")
    gate_result = evaluate_gate(design, build, verify, quality_gate)
    blocked = gate and gate_result.blocked
    forced = bool(gate and blocked and force)
    run_id = _new_run_id(root, spec.sha256, now)

    planned = [f.path for f in design.files if f.path in files]
    code_stems = [PurePosixPath(f.path).stem for f in design.files if f.role == "code"]
    trace_rel = f"{META_DIR}/{code_stems[0] if code_stems else 'run'}.trace.json"

    trace = build_trace(spec, requirements, design, build, verify, run_id=run_id, now=now,
                        forced=forced, gate=gate_result, gated=gate)
    trace["files"] = {p: {"sha256": _sha(files[p])} for p in planned}
    if provenance:
        trace["provenance"] = provenance
    if extra:
        trace.update(extra)

    # plan: targets, actions, diff
    targets = {p: _target(root, p) for p in planned}
    targets[trace_rel] = _target(root, trace_rel)
    contents = {p: files[p] for p in planned}
    trace_text = json.dumps(trace, indent=2, ensure_ascii=False) + "\n"
    contents[trace_rel] = trace_text
    actions, diff_parts = [], []
    for rel in [*planned, trace_rel]:
        old = _read(targets[rel])
        if old is None:
            kind = "created"
        elif old == contents[rel]:
            kind = "unchanged"
        else:
            kind = "overwritten"
        actions.append(FileAction(rel, kind))
        if rel != trace_rel and kind != "unchanged":
            diff_parts.append(_diff(rel, old, contents[rel]))
    diff = "".join(diff_parts)

    hint = f"vishap-generator rollback {run_id}"
    trace_path = str(targets[trace_rel])
    if dry_run or (blocked and not force):
        return DeliverResult(run_id, False, blocked, forced, dry_run, gate_result,
                             tuple(actions), diff, trace, trace_path, hint)

    # write, with a manifest and backups; undo on failure
    run_dir = root / META_DIR / "runs" / run_id
    entries, written_paths = [], []
    run_dir.mkdir(parents=True, exist_ok=False)   # before the try: undo must not touch an older run
    try:
        for a in actions:
            target = targets[a.path]
            entry = {"path": a.path, "action": a.action,
                     "sha256_after": _sha(contents[a.path])}
            if a.action == "overwritten":
                entry["sha256_before"] = _sha(_read(target))
                backup = run_dir / "backup" / Path(*PurePosixPath(a.path).parts)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                entry["backup"] = True
            entries.append(entry)
        manifest = {"id": run_id, "time": now.isoformat(timespec="seconds"),
                    "spec_sha256": spec.sha256, "forced": forced, "rolled_back": False,
                    "files": entries}
        _write_text(run_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")
        for a in actions:
            if a.action == "unchanged":
                continue
            created_dirs = _missing_dirs(root, targets[a.path])
            _write_text(targets[a.path], contents[a.path])
            written_paths.append(a.path)
            for e in entries:
                if e["path"] == a.path:
                    e["new_dirs"] = created_dirs
        _write_text(run_dir / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    except BaseException as exc:
        _undo(root, run_dir, entries, written_paths)
        if isinstance(exc, DeliverError):
            raise
        raise DeliverError(f"write failed, this run was undone: {exc}") from exc

    return DeliverResult(run_id, True, blocked, forced, False, gate_result, tuple(actions),
                         diff, trace, trace_path, hint)


def _new_run_id(root: Path, spec_sha: str, now: dt.datetime) -> str:
    for n in range(100):
        rid = hashlib.sha256(f"{spec_sha}{now.isoformat()}{n}".encode()).hexdigest()[:8]
        if not (root / META_DIR / "runs" / rid).exists():
            return rid
    raise DeliverError("could not pick a free run id")


def _missing_dirs(root: Path, target: Path) -> list[str]:
    out, node = [], target.parent
    while node != root and not node.exists():
        out.append(node.relative_to(root).as_posix())
        node = node.parent
    return out


def _undo(root: Path, run_dir: Path, entries: list[dict], written: list[str]) -> None:
    for e in entries:
        if e["path"] not in written:
            continue
        target = root.joinpath(*PurePosixPath(e["path"]).parts)
        if e["action"] == "created":
            target.unlink(missing_ok=True)
        elif e.get("backup"):
            shutil.copy2(run_dir / "backup" / Path(*PurePosixPath(e["path"]).parts), target)
    _remove_new_dirs(root, entries)
    shutil.rmtree(run_dir, ignore_errors=True)


def _remove_new_dirs(root: Path, entries: list[dict]) -> None:
    """Remove the folders this run created, deepest first, if they are empty."""
    dirs = {d for e in entries for d in e.get("new_dirs", [])}
    for d in sorted(dirs, key=lambda x: x.count("/"), reverse=True):
        try:
            (root / d).rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------- rollback

@dataclass(frozen=True)
class RollbackResult:
    run_id: str
    restored: tuple[str, ...]
    removed: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "restored": list(self.restored),
                "removed": list(self.removed)}


def rollback(out_root: str | os.PathLike, run_id: str, *, force: bool = False) -> RollbackResult:
    root = Path(out_root).resolve()
    if not run_id.isalnum():
        raise DeliverError(f"bad run id: {run_id}")
    run_dir = root / META_DIR / "runs" / run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise DeliverError(f"no run {run_id} in {root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("rolled_back"):
        raise DeliverError(f"run {run_id} was already rolled back")

    changed = []
    for e in manifest["files"]:
        if e["action"] == "unchanged":
            continue
        target = _target(root, e["path"])
        cur = _read(target)
        if cur is None or _sha(cur) != e["sha256_after"]:
            changed.append(e["path"])
    if changed and not force:
        raise DeliverError("changed since this run, not rolling back: " + ", ".join(changed)
                           + " (use force to overwrite)")

    restored, removed = [], []
    for e in manifest["files"]:
        if e["action"] == "unchanged":
            continue
        target = _target(root, e["path"])
        if e["action"] == "created":
            target.unlink(missing_ok=True)
            removed.append(e["path"])
        else:
            shutil.copy2(run_dir / "backup" / Path(*PurePosixPath(e["path"]).parts), target)
            restored.append(e["path"])
    _remove_new_dirs(root, manifest["files"])
    manifest["rolled_back"] = True
    _write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")
    return RollbackResult(run_id, tuple(restored), tuple(removed))
