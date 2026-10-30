# Blind set: the analyzer's rules on independently labelled examples

402 frozen examples from three sources (OWASP Benchmark for Java, DVWA, Bandit's examples), registered before the first run (`CRITERION.md`, `SAMPLING.md`, `frozen_ids.sha256`). The files are downloaded from pinned URLs and checked against the manifest's SHA-256; they are not in this repository.

**What this measures:** the rule engine alone. It does not measure the hub's verdicts with a model; that is `model_eval.py`, paid and not part of CI. A result here says nothing about a hub run that used a model.

**SAFE** is issued only for a language that passed the gates below, for a text the scan could read in full, with no finding. `raw SAFE` in the tables is the first two of those without the language gate: no finding and a complete scan. It is what the gates are about.

## Gates and the decision per language

Keyed by the language the engine detects when text is pasted without a file name, which is how the hub calls it.

| language | dangerous | safe | false-SAFE | critical false-SAFE | 95% upper bound | review burden | measured | SAFE allowed | why |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| javascript | 7 | 1 | 4 | 1 | 84.2% | 0% | no | **no** | unmeasured: 7 dangerous and 1 safe examples, 20 and 20 are needed |
| python | 205 | 135 | 146 | 27 | 77.0% | 10% | yes | **no** | G1 failed: 27 critical example(s) got SAFE |

**SAFE cannot be issued for any language.** Every verdict the rules produce is REQUIRES_REVIEW until a language passes.
Languages with no source here (JavaScript, TypeScript, Go, C, C++, Terraform, YAML, Dockerfile) are unmeasured, so SAFE is never issued for them.

## By the example's true language, file name given (what an upload would see)

Informational: the hub does not call the engine this way. Same gates, same counts.

| language | dangerous | safe | false-SAFE | critical false-SAFE | 95% upper bound | G1 | G2 |
|---|---:|---:|---:|---:|---:|---|---|
| java | 132 | 132 | 101 | 12 | 82.9% | FAIL | FAIL |
| php | 38 | 19 | 29 | 8 | 87.0% | FAIL | FAIL |
| python | 76 | 5 | 44 | 15 | 68.3% | FAIL | FAIL |

## Mode `named` (file name given)

| source | language | label | criticality | examples | raw SAFE | right class found |
|---|---|---|---|---:|---:|---:|
| bandit | python | dangerous | critical | 24 | 15 (62%) | - |
| bandit | python | dangerous | high | 35 | 21 (60%) | - |
| bandit | python | dangerous | medium | 17 | 8 (47%) | - |
| bandit | python | safe | none | 5 | 4 (80%) | - |
| benchmark | java | dangerous | critical | 24 | 12 (50%) | 12 |
| benchmark | java | dangerous | high | 60 | 60 (100%) | 0 |
| benchmark | java | dangerous | medium | 48 | 29 (60%) | 12 |
| benchmark | java | safe | none | 132 | 115 (87%) | - |
| dvwa | php | dangerous | critical | 10 | 8 (80%) | - |
| dvwa | php | dangerous | high | 12 | 10 (83%) | - |
| dvwa | php | dangerous | medium | 16 | 11 (69%) | - |
| dvwa | php | safe | none | 19 | 15 (79%) | - |

Time per example: median 4.53 ms, max 41.61 ms.

OWASP Benchmark, dangerous examples called raw SAFE by category (mode `named`): cmdi 11/12, crypto 0/12, hash 5/12, ldapi 12/12, pathtraver 12/12, securecookie 12/12, sqli 1/12, trustbound 12/12, weakrand 12/12, xpathi 12/12, xss 12/12.

## Mode `pasted` (pasted, language sniffed)

| source | language | label | criticality | examples | raw SAFE | right class found |
|---|---|---|---|---:|---:|---:|
| bandit | python | dangerous | critical | 24 | 14 (58%) | - |
| bandit | python | dangerous | high | 35 | 21 (60%) | - |
| bandit | python | dangerous | medium | 17 | 7 (41%) | - |
| bandit | python | safe | none | 5 | 1 (20%) | - |
| benchmark | java | dangerous | critical | 24 | 13 (54%) | 11 |
| benchmark | java | dangerous | high | 60 | 60 (100%) | 0 |
| benchmark | java | dangerous | medium | 48 | 29 (60%) | 12 |
| benchmark | java | safe | none | 132 | 119 (90%) | - |
| dvwa | php | dangerous | critical | 10 | 1 (10%) | - |
| dvwa | php | dangerous | high | 12 | 0 (0%) | - |
| dvwa | php | dangerous | medium | 16 | 5 (31%) | - |
| dvwa | php | safe | none | 19 | 2 (11%) | - |

Time per example: median 11.96 ms, max 71.87 ms.

OWASP Benchmark, dangerous examples called raw SAFE by category (mode `pasted`): cmdi 12/12, crypto 0/12, hash 5/12, ldapi 12/12, pathtraver 12/12, securecookie 12/12, sqli 1/12, trustbound 12/12, weakrand 12/12, xpathi 12/12, xss 12/12.

## Examples added after the first run: 0

None.

## Left out of the sample, and why

- {'file': 'skip.py', 'reason': 'checked more than once: first expectation kept'}
- {'test': 'test_multiline_sql_statements', 'reason': 'example file name is not a literal'}
- {'file': 'assert.py', 'reason': 'checked more than once: first expectation kept'}
- {'file': 'assert.py', 'reason': 'checked more than once: first expectation kept'}
- {'file': 'try_except_continue.py', 'reason': 'checked more than once: first expectation kept'}
- {'file': 'try_except_pass.py', 'reason': 'checked more than once: first expectation kept'}
