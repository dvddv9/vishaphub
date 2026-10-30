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

## HTTP service

`python -m validator.server` serves `GET /health`, `GET /` and `POST /check`. `/check` **runs the deliverable's
own tests**, so it is closed by default:

- it answers `503` until `VISHAP_VALIDATOR_TOKEN` (at least 24 characters) is set, and `401` without
  `Authorization: Bearer <token>`; the token is checked before the body is read;
- at most `VISHAP_VALIDATOR_MAX_CONCURRENT` (2) checks at once, the rest get `503`; at most 200 files and 8 MB
  per request; a client that stops sending is dropped after 30 s;
- a bare run listens on `127.0.0.1`; the image sets `VISHAP_VALIDATOR_HOST=0.0.0.0`.

The service runs submitted code only where the OS can cut the network off (a network namespace, `unshare -n`);
elsewhere `POST /check` refuses and says so. It is still not a full sandbox, see "Isolation of the code under test".
`render.yaml` has `autoDeploy: false` for that reason; the hub does not need this service, it calls the
validator as a library. The hub wrapper also requires a real network namespace by default; until the
runtime provides one, its validation stage fails closed before running submitted tests.

## Isolation of the code under test

`behavior` and `contract` run someone else's code. Three layers, and each run says which network layer it had
(`note: "network: netns|guard|none"` on the check):

| layer | what it stops | where it works |
|---|---|---|
| network namespace (`unshare -n`) | the whole network, including `ctypes`, raw sockets, `curl` | Linux with the privilege; **not** a non-root user in a container (checked in the hub image) |
| socket guard (`_netguard.py`, loaded as `sitecustomize`) | every non-UNIX socket: `requests`, `urllib`, `socket`, DNS, listening | everywhere, no privilege |
| resource caps (`setrlimit`: CPU, memory, file size, processes) | a fork bomb, a memory hog, a huge file | POSIX |

The guard stops the ordinary ways out, not a hostile test that goes round it (`ctypes`, the raw `_socket`
module, a `curl` subprocess). For those, run the container itself without a network:
`docker run --read-only --network none --pids-limit 256 --memory 1g ...`.

- `VISHAP_VALIDATOR_REQUIRE_NETNS=1` (and always for `POST /check`): without a real network namespace nothing
  submitted is run; the report is FAIL, "nothing was run".
- `VISHAP_VALIDATOR_NO_NETWORK=0` switches the guard and the namespace off (local debugging only).
- On Windows `socketpair` is TCP on loopback, so the guard refuses it; asyncio code under test needs POSIX.
- Not isolated: the disk the process can reach, and loopback services of the host in the namespace-less case
  are closed by the guard but reachable by anything that goes round it.

## Design rules

- **No network, no LLM.** A validator that needs a model to say «pass» is not a validator.
- **Read-only.** The deliverable is never modified; pytest gets an empty ini from the temp dir.
- **The code under test is someone else's code.** `behavior` and `contract` run it in a subprocess with a clean
  environment (`PATH`, temp dirs, locale - never the host's keys or database URLs), and a spec path that is
  absolute, climbs with `..` or is not a dotted module name is refused before anything runs. What this does
  not do: see "Isolation of the code under test" - the disk the process can reach is still reachable.
- **Bounded.** Import probe 60 s, test run 120 s.
- **One concern per module**, so a failing check names the thing that broke.

## Status

`0.3.0` - six checks plus the spec guard, end to end on the bundled examples; `pytest` covers each stage and
the isolation rules (`tests/`).
