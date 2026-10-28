# Vishap Validator

Answers one question: **does the generated code do what the spec promised?**

It is not an analyser. The analyser asks «is it dangerous»; the validator asks
«does it match the promise» — files, names, behaviour. It never re-audits
security and never rewrites the code.

## What it checks

| Check | Question | Severity on failure |
|---|---|---|
| `structure` | are the promised files present and non-empty? | critical |
| `syntax` | does every `.py` file parse? | critical |
| `contract` | do the promised names import from the entry point? | critical / high |
| `behaviour` | do the spec's tests run and pass? | high |

`structure` and `syntax` stop the run: behaviour on code that does not parse is noise.

## Verdict

| Findings | Verdict |
|---|---|
| any critical | `FAIL` |
| any high / medium / low | `NEEDS_REVIEW` |
| none | `PASS` |
| validator itself crashed | `ERROR` — never `PASS` |

A check that did not run never looks like a check that passed.

## Spec

```json
{
  "language": "python",
  "files": ["calc/__init__.py", "test_calc.py"],
  "exports": ["add"],
  "entry": "calc",
  "tests": ["test_calc.py"]
}
```

Unknown keys are rejected — a typo in a spec must not silently disable a check.

## Usage

```bash
pip install -e .
vishap-validator check ./out --spec spec.json
vishap-validator check ./out --spec spec.json --json --report-out report.json
```

Exit code: `0` for `PASS` and `NEEDS_REVIEW`, `1` for `FAIL` and `ERROR`.

## Design rules

- **No network, no LLM.** A validator that needs a model to say «pass» is not a validator.
- **Read-only.** The deliverable is never modified; pytest gets an empty ini from the temp dir.
- **Bounded.** Import probe 60 s, test run 120 s.
- **One concern per module**, so a failing check names the thing that broke.

## Status

`0.1.0` — the four checks work end to end on the bundled examples. The test suite
is deliberately left for the end of the build.
