# How the blind set is drawn (registered before any example file is fetched or scored)

Committed after `CRITERION.md` and before any example was downloaded. Only the sources' own label files had been
fetched at this point (the Benchmark's expected-results CSV, to read its categories); no example was opened and the
rules have not been run on any of it. Everything below is a rule, not a choice made while looking.

Sources are pinned to a commit and are **not copied into this repository** (their licences differ from ours:
GPL-2.0, GPL-3.0, Apache-2.0). A manifest records, for each example, the pinned URL and the SHA-256 of the file;
the benchmark downloads it and refuses a file whose hash differs.

| source | pinned commit | licence | language |
|---|---|---|---|
| OWASP Benchmark for Java 1.2 (`OWASP-Benchmark/BenchmarkJava`) | `f40c618c5a709afce350ef06ed2899c85cf586e9` | GPL-2.0 | Java |
| DVWA (`digininja/DVWA`) | `a1978a2fed195acd093010af6395f86a281537ca` | GPL-3.0 | PHP |
| Bandit examples (`PyCQA/bandit`) | `48ef27bd1bbc32f4e585c92310f7a574e87f6b04` | Apache-2.0 | Python |

## OWASP Benchmark (Java)

Label: the project's own `expectedresults-1.2.csv`, column "real vulnerability": `true` is dangerous, `false` is safe
(the project's decoys, written to look like the vulnerable ones).
Sample: for each category, sort the test names by SHA-256 of the name, take the first 12 dangerous and the first 12
safe (fewer if the category has fewer).
Criticality of a dangerous one, by category: `sqli`, `cmdi` -> critical; `pathtraver`, `xss`, `ldapi`, `xpathi`,
`trustbound` -> high; `hash`, `crypto`, `weakrand`, `securecookie` -> medium.

## DVWA (PHP)

Label: the project's own design. In each `vulnerabilities/<name>/source/`, `low.php` and `medium.php` are
dangerous, `impossible.php` is safe. `high.php` is left out: it is a partial mitigation, neither.
Sample: every vulnerability directory that has these files.
Criticality by directory: `sqli`, `sqli_blind`, `exec`, `fi`, `upload` -> critical; `xss_r`, `xss_s`, `xss_d`, `csrf`,
`authbypass`, `open_redirect` -> high; every other directory -> medium.

## Bandit examples (Python)

Label: the expectations in the project's own `tests/functional/test_functional.py`, one per example file. An example
whose expected issue count is zero is safe; otherwise it is dangerous, and its criticality is the worst expected
severity: HIGH -> critical, MEDIUM -> high, LOW -> medium.
Sample: every example file for which the functional tests state an expectation.
A file the expectations cannot be read for is left out and the reason is listed in the manifest, not silently dropped.

## Not in the blind set

JavaScript, TypeScript, Go, C, C++, Terraform, YAML and Dockerfile have no source here. They are **unmeasured**, and
by the criterion SAFE is never issued for an unmeasured language.

## After the first scoring

Examples may be added, never removed. An added example carries `post_run: true`, is scored and reported on its own
line, and is not counted in any gate (`CRITERION.md`).
