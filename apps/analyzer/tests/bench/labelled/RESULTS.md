# Labelled benchmark: the analyzer's rules alone

105 examples (71 dangerous, 34 safe), 11 languages. Produced by `python -m tests.bench.labelled_score --write`; the examples, their expected findings and the reason for each label are in `manifest.json`.

## What this does and does not measure

The built-in rule engine of the analyzer (src/tools/static_scan.scan_material): no model, no network. Languages: those the engine has rules or detection for. Go has only the language-independent rules.

**It does not measure the hub's verdicts with a model.** In the hub the model proposes and the rules decide, and none of that runs here: no model, no network, no key. The numbers below say what the rules do alone. They say nothing about the quality of a hub run that used a model, in either direction.

SAFE means what it means in the hub: the rules found nothing at all. A finding on the wrong line, or of the wrong class, is a miss but not SAFE.

**Release blocker:** no example labelled critical may get SAFE, in either mode (`tests/test_bench_labelled.py`).

### Blocker status

**BLOCKED** - 4 critical example(s) got SAFE:
- named: php-cmd-system (php)
- named: php-eval-post (php)
- named: go-cmd-sh-c (go)
- pasted: go-cmd-sh-c (go)

## Mode `named` (file name given, as an upload)

### Dangerous examples, by language and criticality

| language | criticality | examples | found | recall (findings) | right class, wrong line | SAFE |
|---|---|---:|---:|---:|---:|---:|
| c | critical | 2 | 2 | 100% (2/2) | 0 | 0 |
| c | high | 5 | 3 | 60% (3/5) | 0 | 2 |
| cpp | critical | 1 | 1 | 100% (1/1) | 0 | 0 |
| cpp | high | 2 | 1 | 50% (1/2) | 0 | 1 |
| dockerfile | high | 1 | 0 | 0% (0/1) | 0 | 1 |
| dockerfile | medium | 1 | 0 | 0% (0/1) | 0 | 1 |
| dockerfile | low | 1 | 0 | 0% (0/1) | 0 | 1 |
| go | critical | 2 | 1 | 50% (1/2) | 0 | 1 |
| go | high | 2 | 1 | 50% (1/2) | 0 | 1 |
| go | medium | 2 | 0 | 0% (0/2) | 0 | 2 |
| java | critical | 3 | 3 | 100% (3/3) | 0 | 0 |
| java | high | 3 | 1 | 33% (1/3) | 0 | 2 |
| java | medium | 1 | 1 | 100% (1/1) | 0 | 0 |
| javascript | critical | 3 | 3 | 100% (3/3) | 0 | 0 |
| javascript | high | 4 | 3 | 75% (3/4) | 0 | 1 |
| javascript | medium | 2 | 2 | 100% (2/2) | 0 | 0 |
| php | critical | 3 | 0 | 0% (0/3) | 0 | 2 |
| php | high | 3 | 1 | 33% (1/3) | 0 | 2 |
| python | critical | 7 | 7 | 100% (7/7) | 0 | 0 |
| python | high | 8 | 4 | 50% (4/8) | 0 | 3 |
| python | medium | 4 | 4 | 100% (4/4) | 0 | 0 |
| terraform | high | 3 | 3 | 100% (3/3) | 0 | 0 |
| terraform | medium | 1 | 1 | 100% (1/1) | 0 | 0 |
| typescript | critical | 2 | 2 | 100% (2/2) | 0 | 0 |
| typescript | high | 2 | 1 | 50% (1/2) | 0 | 1 |
| yaml | high | 3 | 2 | 67% (2/3) | 0 | 1 |

Overall recall: 66% (47/71 expected findings). Without the examples the rules were written for after the first run (`rules_written_after` in the manifest): 66% (47/71).

### Safe examples: false positives

| language | examples | with findings | findings | critical | high | medium | low |
|---|---:|---:|---:|---:|---:|---:|---:|
| c | 3 | 1 | 1 | 0 | 1 | 0 | 0 |
| cpp | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| dockerfile | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| go | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| java | 4 | 1 | 1 | 0 | 1 | 0 | 0 |
| javascript | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| php | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| python | 6 | 1 | 1 | 0 | 1 | 0 | 0 |
| terraform | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| typescript | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| yaml | 2 | 0 | 0 | 0 | 0 | 0 | 0 |

### Language detection and time

| language | examples | language detected | median ms | max ms |
|---|---:|---:|---:|---:|
| c | 10 | 10/10 | 0.41 | 0.52 |
| cpp | 5 | 5/5 | 0.21 | 0.24 |
| dockerfile | 5 | 5/5 | 0.23 | 0.32 |
| go | 9 | 9/9 | 0.3 | 0.6 |
| java | 11 | 11/11 | 0.45 | 0.92 |
| javascript | 13 | 13/13 | 0.68 | 0.93 |
| php | 9 | 9/9 | 0.14 | 0.35 |
| python | 25 | 25/25 | 1.8 | 3.22 |
| terraform | 6 | 6/6 | 0.27 | 0.52 |
| typescript | 7 | 7/7 | 0.52 | 0.7 |
| yaml | 5 | 5/5 | 0.56 | 0.64 |

### Misses in mode `named` (24 examples with an expected finding not hit)

- `go-cmd-sh-c` (go, critical): 0/1 hit, SAFE
- `php-cmd-system` (php, critical): 0/1 hit, SAFE
- `php-eval-post` (php, critical): 0/1 hit, SAFE
- `php-sqli-concat` (php, critical): 0/1 hit, 1 other finding(s)
- `c-malloc-overflow` (c, high): 0/1 hit, SAFE
- `c-use-after-free` (c, high): 0/1 hit, SAFE
- `cpp-format-string` (cpp, high): 0/1 hit, SAFE
- `docker-secret-in-env` (dockerfile, high): 0/1 hit, SAFE
- `go-path-traversal` (go, high): 0/1 hit, SAFE
- `java-path-traversal` (java, high): 0/1 hit, SAFE
- `java-xxe-default-parser` (java, high): 0/1 hit, SAFE
- `js-jwt-none` (javascript, high): 0/1 hit, SAFE
- `k8s-plaintext-secret-env` (yaml, high): 0/1 hit, SAFE
- `php-include-lfi` (php, high): 0/1 hit, SAFE
- `php-reflected-xss` (php, high): 0/1 hit, SAFE
- `py-idor` (python, high): 0/1 hit, SAFE
- `py-path-traversal` (python, high): 0/1 hit, 1 other finding(s)
- `py-ssrf` (python, high): 0/1 hit, SAFE
- `py-xss-flask` (python, high): 0/1 hit, SAFE
- `ts-reflected-xss` (typescript, high): 0/1 hit, SAFE
- `docker-curl-pipe-sh` (dockerfile, medium): 0/1 hit, SAFE
- `go-math-rand-token` (go, medium): 0/1 hit, SAFE
- `go-md5-password` (go, medium): 0/1 hit, SAFE
- `docker-runs-as-root` (dockerfile, low): 0/1 hit, SAFE

### False positives in mode `named` (3 safe examples flagged)

- `py-safe-subprocess-list`: cmd-injection-py line 14 (high)
- `java-safe-processbuilder-validated`: cmd-injection-java line 10 (high)
- `c-safe-execvp`: cmd-injection-c line 11 (high)

## Mode `pasted` (no file name, language sniffed - what the hub does with pasted code)

### Dangerous examples, by language and criticality

| language | criticality | examples | found | recall (findings) | right class, wrong line | SAFE |
|---|---|---:|---:|---:|---:|---:|
| c | critical | 2 | 2 | 100% (2/2) | 0 | 0 |
| c | high | 5 | 3 | 60% (3/5) | 0 | 2 |
| cpp | critical | 1 | 1 | 100% (1/1) | 0 | 0 |
| cpp | high | 2 | 1 | 50% (1/2) | 0 | 1 |
| dockerfile | high | 1 | 0 | 0% (0/1) | 0 | 1 |
| dockerfile | medium | 1 | 0 | 0% (0/1) | 0 | 1 |
| dockerfile | low | 1 | 0 | 0% (0/1) | 0 | 1 |
| go | critical | 2 | 1 | 50% (1/2) | 0 | 1 |
| go | high | 2 | 1 | 50% (1/2) | 0 | 1 |
| go | medium | 2 | 0 | 0% (0/2) | 0 | 2 |
| java | critical | 3 | 3 | 100% (3/3) | 0 | 0 |
| java | high | 3 | 1 | 33% (1/3) | 0 | 2 |
| java | medium | 1 | 1 | 100% (1/1) | 0 | 0 |
| javascript | critical | 3 | 3 | 100% (3/3) | 0 | 0 |
| javascript | high | 4 | 3 | 75% (3/4) | 0 | 1 |
| javascript | medium | 2 | 2 | 100% (2/2) | 0 | 0 |
| php | critical | 3 | 2 | 67% (2/3) | 0 | 0 |
| php | high | 3 | 1 | 33% (1/3) | 0 | 2 |
| python | critical | 7 | 7 | 100% (7/7) | 0 | 0 |
| python | high | 8 | 4 | 50% (4/8) | 0 | 3 |
| python | medium | 4 | 4 | 100% (4/4) | 0 | 0 |
| terraform | high | 3 | 3 | 100% (3/3) | 0 | 0 |
| terraform | medium | 1 | 1 | 100% (1/1) | 0 | 0 |
| typescript | critical | 2 | 2 | 100% (2/2) | 0 | 0 |
| typescript | high | 2 | 1 | 50% (1/2) | 0 | 1 |
| yaml | high | 3 | 2 | 67% (2/3) | 0 | 1 |

Overall recall: 69% (49/71 expected findings). Without the examples the rules were written for after the first run (`rules_written_after` in the manifest): 69% (49/71).

### Safe examples: false positives

| language | examples | with findings | findings | critical | high | medium | low |
|---|---:|---:|---:|---:|---:|---:|---:|
| c | 3 | 1 | 1 | 0 | 1 | 0 | 0 |
| cpp | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| dockerfile | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| go | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| java | 4 | 1 | 1 | 0 | 1 | 0 | 0 |
| javascript | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| php | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| python | 6 | 1 | 1 | 0 | 1 | 0 | 0 |
| terraform | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| typescript | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| yaml | 2 | 0 | 0 | 0 | 0 | 0 | 0 |

### Language detection and time

| language | examples | language detected | median ms | max ms |
|---|---:|---:|---:|---:|
| c | 10 | 10/10 | 0.48 | 0.59 |
| cpp | 5 | 0/5 | 0.25 | 0.3 |
| dockerfile | 5 | 0/5 | 0.64 | 0.8 |
| go | 9 | 0/9 | 0.79 | 1.29 |
| java | 11 | 11/11 | 0.58 | 1.16 |
| javascript | 13 | 13/13 | 0.76 | 1.02 |
| php | 9 | 0/9 | 0.35 | 0.67 |
| python | 25 | 25/25 | 1.8 | 3.58 |
| terraform | 6 | 6/6 | 0.34 | 0.72 |
| typescript | 7 | 0/7 | 0.61 | 0.76 |
| yaml | 5 | 5/5 | 0.69 | 0.88 |

### Misses in mode `pasted` (22 examples with an expected finding not hit)

- `go-cmd-sh-c` (go, critical): 0/1 hit, SAFE
- `php-sqli-concat` (php, critical): 0/1 hit, 1 other finding(s)
- `c-malloc-overflow` (c, high): 0/1 hit, SAFE
- `c-use-after-free` (c, high): 0/1 hit, SAFE
- `cpp-format-string` (cpp, high): 0/1 hit, SAFE
- `docker-secret-in-env` (dockerfile, high): 0/1 hit, SAFE
- `go-path-traversal` (go, high): 0/1 hit, SAFE
- `java-path-traversal` (java, high): 0/1 hit, SAFE
- `java-xxe-default-parser` (java, high): 0/1 hit, SAFE
- `js-jwt-none` (javascript, high): 0/1 hit, SAFE
- `k8s-plaintext-secret-env` (yaml, high): 0/1 hit, SAFE
- `php-include-lfi` (php, high): 0/1 hit, SAFE
- `php-reflected-xss` (php, high): 0/1 hit, SAFE
- `py-idor` (python, high): 0/1 hit, SAFE
- `py-path-traversal` (python, high): 0/1 hit, 1 other finding(s)
- `py-ssrf` (python, high): 0/1 hit, SAFE
- `py-xss-flask` (python, high): 0/1 hit, SAFE
- `ts-reflected-xss` (typescript, high): 0/1 hit, SAFE
- `docker-curl-pipe-sh` (dockerfile, medium): 0/1 hit, SAFE
- `go-math-rand-token` (go, medium): 0/1 hit, SAFE
- `go-md5-password` (go, medium): 0/1 hit, SAFE
- `docker-runs-as-root` (dockerfile, low): 0/1 hit, SAFE

### False positives in mode `pasted` (3 safe examples flagged)

- `py-safe-subprocess-list`: cmd-injection-py line 14 (high)
- `java-safe-processbuilder-validated`: cmd-injection-java line 10 (high)
- `c-safe-execvp`: cmd-injection-c line 11 (high)

Timings are the fastest of three runs on whatever machine produced this file; they are not compared between runs. Everything else in this file is deterministic.
