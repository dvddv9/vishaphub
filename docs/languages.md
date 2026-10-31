# Language support is a measured claim

The hub has no list of "supported languages" that someone typed in. What it can say about a language is what a
labelled benchmark measured: examples with a label (dangerous or safe), an expected finding and a reason, in
`apps/analyzer/tests/bench/labelled` (rules alone: no model, no network).

## What a run says

Every run that read code records, for each language the rules read, how that language is measured
(`checks.analyser.languages`, and inside the hashed evidence of the fingerprint). The report page, the Markdown
export and `GET /api/languages` show it in words:

| Adequacy | Rule (not opinion) | What it means |
|---|---|---|
| `measured` | at least 10 dangerous and 5 safe labelled examples | enough to see a miss and a false alarm; still a small set, never a guarantee about your code |
| `thin` | some, fewer than that | the counts are shown as counts: a percentage of three examples is not a rate |
| `none` | no labelled example | nothing is known about how often the rules miss |

The hub sends only text to the rules, so the numbers are the benchmark's `pasted` mode.

## In a pipeline

`--require-measured` (CLI) or `"require_measured": true` (HTTP) turns the evidence into a gate: a run that read a
language whose adequacy is not `measured` ends with exit code 3 and says which language and how many examples
stand behind it. A failing verdict still wins. Without the flag nothing changes, and `ci.languages` still shows the
adequacy of each language the run read.

## The rule for adding a language

No rules without data. A language can get rules in the analyzer only together with labelled examples, dangerous
and safe, in the benchmark. Three tests hold the line (`apps/hub/tests/test_languages.py`):

1. every language the engine has rules for has labelled examples, or is named in `hub.languages.EXEMPT` with a
   written reason (today only `log`: log lines are checked for attack patterns, not read as code);
2. an exemption goes stale the day data arrives: the test fails until it is removed;
3. a labelled language has both dangerous and safe examples (without safe ones nothing can say how often the
   rules cry wolf), and the hub's copy of the counts equals the benchmark's current ones.

After changing the benchmark: `python apps/hub/scripts/language_evidence.py --write`, commit the result. The test
fails on a stale copy.

## What it showed on 31 Oct 2026

- Only Python reaches `measured`. JavaScript (9 dangerous, 4 safe), Java and the rest are `thin`; Dockerfile hit
  0 of 3 expected findings.
- The language is recognised from the text alone for Python, JavaScript, Java and YAML. Go, PHP and Dockerfile
  material comes through as `unknown`: only the language-independent rules ran on it, and the evidence says so.
  A file name would fix the recognition; the hub does not send one yet.
- The benchmark's own release blocker (no critical example may get SAFE) holds; the benchmark counts are in
  `GET /api/languages`.