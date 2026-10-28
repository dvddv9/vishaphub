"""SARIF 2.1.0 for the result of a run, so a pipeline can show it.

One result per failed or unproven critical/high requirement, one per
failed piece of evidence, and one per open gap. Locations point at the
spec line the requirement came from.
"""

from __future__ import annotations

LEVEL = {"critical": "error", "high": "error", "medium": "warning"}


def to_sarif(result, spec_name: str) -> dict:
    rules: dict[str, dict] = {}
    out: list[dict] = []

    def add(rule_id: str, text: str, level: str, line: int | None, title: str) -> None:
        rules.setdefault(rule_id, {"id": rule_id, "shortDescription": {"text": title}})
        loc = {"physicalLocation": {"artifactLocation": {"uri": spec_name}}}
        if line:
            loc["physicalLocation"]["region"] = {"startLine": line}
        out.append({"ruleId": rule_id, "level": level, "message": {"text": text},
                    "locations": [loc]})

    lines = {r.id: r.source.line for r in result.requirements}
    if result.verify:
        for v in result.verify.requirements:
            if v.status == "passed":
                continue
            level = LEVEL.get(v.priority, "warning")
            if v.status != "failed":
                level = "warning"
            for e in v.evidence:
                if e.status in ("fail", "error"):
                    add(f"requirement/{v.id}", f"{v.id}: {e.source} {e.name}: {e.detail}".strip(),
                        level, lines.get(v.id), "Requirement not met")
            if not any(e.status in ("fail", "error") for e in v.evidence):
                add(f"requirement/{v.id}", f"{v.id} is {v.status}. {v.note}".strip(),
                    "warning", lines.get(v.id), "Requirement not proven")
    if result.design:
        for g in result.design.gaps:
            add(f"gap/{g.type}", f"{g.id}: {g.text}",
                "error" if g.severity == "critical" else "note",
                g.source.line if g.source else None, "Gap in the specification")
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "vishap-generator", "rules": list(rules.values())}},
                  "results": out}],
    }
