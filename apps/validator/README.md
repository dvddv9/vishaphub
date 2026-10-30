# Vishap Validator

Answers one question: **does the generated code do what the spec promised?**

It is not an analyser. The analyser asks «is it dangerous»; the validator asks
«does it match the promise» — files, names, behaviour. It never re-audits
security and never rewrites the code.

## What it checks

| Check | Question | Severity on failure |
|---|---|---|
| `spec` | does the spec stay inside the deliverable? (before anything is read or run) | critical |
| `structure` | are the promised files present and non-empty? | critical / high |
| `syntax` | does every `.py` file parse? | critical |
| `contract` | do the promised names import from the entry point? | critical / high |
| `coverage` | does any test mention each public name? | medium |
| `behavior` | do the spec's tests run, and did at least one pass? | high |
| `conformance` | is the promised code real, or a stub / placeholder? | high / low |

`spec`, `structure` and `syntax` stop the run: later checks on code that is missing or does not parse are noise.
`behavior` is not green when pytest exits 0 but nothing passed (everything skipped).
`conformance` looks for TODO / FIXME / "stub" / "not implemented" in comments only, as whole words.

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
- **The code under test is someone else's code.** `behavior` and `contract` run it in a subprocess with a clean
  environment (`PATH`, temp dirs, locale - never the host's keys or database URLs), and a spec path that is
  absolute, climbs with `..` or is not a dotted module name is refused before anything runs. What this does
  not do: it is not a sandbox - the code can still use the network and the disk the process can reach. Run the
  validator on untrusted input only inside an isolated container.
- **Bounded.** Import probe 60 s, test run 120 s.
- **One concern per module**, so a failing check names the thing that broke.

## Status

`0.3.0` - six checks plus the spec guard, end to end on the bundled examples; `pytest` covers each stage and
the isolation rules (`tests/`).
