# Blind set: the analyzer's rules on independently labelled examples

402 frozen examples from three sources (OWASP Benchmark for Java, DVWA, Bandit's examples), registered before the first run (`CRITERION.md`, `SAMPLING.md`, `frozen_ids.sha256`). The files are downloaded from pinned URLs and checked against the manifest's SHA-256; they are not in this repository.

**What this measures:** the rule engine alone. It does not measure the hub's verdicts with a model; that is `model_eval.py`, paid and not part of CI. A result here says nothing about a hub run that used a model.

**SAFE** is issued only for a language that passed the gates below, for a text the scan could read in full, with no finding. `raw SAFE` in the tables is the first two of those without the language gate: no finding and a complete scan. It is what the gates are about.

## Gates and the decision per language

Keyed by the language the engine detects when text is pasted without a file name, which is how the hub calls it.

| language | dangerous | safe | false-SAFE | critical false-SAFE | 95% upper bound | review burden | measured | SAFE allowed | why |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| java | 132 | 132 | 0 | 0 | 2.8% | 98% | yes | **yes** | passed G1 and G2 |
| php | 38 | 18 | 21 | 4 | 69.8% | 28% | no | **no** | unmeasured: 38 dangerous and 18 safe examples, 20 and 20 are needed |
| python | 71 | 2 | 12 | 0 | 27.3% | 100% | no | **no** | unmeasured: 71 dangerous and 2 safe examples, 20 and 20 are needed |

SAFE can be issued for: java.
Languages with no source here (JavaScript, TypeScript, Go, C, C++, Terraform, YAML, Dockerfile) are unmeasured, so SAFE is never issued for them.

## By the example's true language, file name given (what an upload would see)

Informational: the hub does not call the engine this way. Same gates, same counts.

| language | dangerous | safe | false-SAFE | critical false-SAFE | 95% upper bound | G1 | G2 |
|---|---:|---:|---:|---:|---:|---|---|
| java | 132 | 132 | 0 | 0 | 2.8% | pass | pass |
| php | 38 | 19 | 21 | 4 | 69.8% | FAIL | FAIL |
| python | 76 | 5 | 13 | 1 | 27.1% | FAIL | FAIL |

## Mode `named` (file name given)

| source | language | label | criticality | examples | raw SAFE | right class found |
|---|---|---|---|---:|---:|---:|
| bandit | python | dangerous | critical | 24 | 1 (4%) | - |
| bandit | python | dangerous | high | 35 | 9 (26%) | - |
| bandit | python | dangerous | medium | 17 | 3 (18%) | - |
| bandit | python | safe | none | 5 | 3 (60%) | - |
| benchmark | java | dangerous | critical | 24 | 0 (0%) | 24 |
| benchmark | java | dangerous | high | 60 | 0 (0%) | 48 |
| benchmark | java | dangerous | medium | 48 | 0 (0%) | 24 |
| benchmark | java | safe | none | 132 | 3 (2%) | - |
| dvwa | php | dangerous | critical | 10 | 4 (40%) | - |
| dvwa | php | dangerous | high | 12 | 8 (67%) | - |
| dvwa | php | dangerous | medium | 16 | 9 (56%) | - |
| dvwa | php | safe | none | 19 | 14 (74%) | - |

Time per example: median 4.48 ms, max 26.15 ms.

OWASP Benchmark, dangerous examples called raw SAFE by category (mode `named`): cmdi 0/12, crypto 0/12, hash 0/12, ldapi 0/12, pathtraver 0/12, securecookie 0/12, sqli 0/12, trustbound 0/12, weakrand 0/12, xpathi 0/12, xss 0/12.

## Mode `pasted` (pasted, language sniffed)

| source | language | label | criticality | examples | raw SAFE | right class found |
|---|---|---|---|---:|---:|---:|
| bandit | python | dangerous | critical | 24 | 0 (0%) | - |
| bandit | python | dangerous | high | 35 | 9 (26%) | - |
| bandit | python | dangerous | medium | 17 | 3 (18%) | - |
| bandit | python | safe | none | 5 | 0 (0%) | - |
| benchmark | java | dangerous | critical | 24 | 0 (0%) | 24 |
| benchmark | java | dangerous | high | 60 | 0 (0%) | 48 |
| benchmark | java | dangerous | medium | 48 | 0 (0%) | 24 |
| benchmark | java | safe | none | 132 | 3 (2%) | - |
| dvwa | php | dangerous | critical | 10 | 4 (40%) | - |
| dvwa | php | dangerous | high | 12 | 8 (67%) | - |
| dvwa | php | dangerous | medium | 16 | 9 (56%) | - |
| dvwa | php | safe | none | 19 | 13 (68%) | - |

Time per example: median 4.59 ms, max 22.68 ms.

OWASP Benchmark, dangerous examples called raw SAFE by category (mode `pasted`): cmdi 0/12, crypto 0/12, hash 0/12, ldapi 0/12, pathtraver 0/12, securecookie 0/12, sqli 0/12, trustbound 0/12, weakrand 0/12, xpathi 0/12, xss 0/12.

## Examples added after the first run: 0

None.

## Known flaws in the sample

1 example(s) are empty files in their source (dvwa:javascript/impossible). The sampling rule had no exception for an empty file and the rules say an example is never removed after the first run, so it is kept and counted as the source labelled it. It is a defect of the sample, not a finding about the rules.

## Left out of the sample, and why

- {'file': 'skip.py', 'reason': 'checked more than once: first expectation kept'}
- {'test': 'test_multiline_sql_statements', 'reason': 'example file name is not a literal'}
- {'file': 'assert.py', 'reason': 'checked more than once: first expectation kept'}
- {'file': 'assert.py', 'reason': 'checked more than once: first expectation kept'}
- {'file': 'try_except_continue.py', 'reason': 'checked more than once: first expectation kept'}
- {'file': 'try_except_pass.py', 'reason': 'checked more than once: first expectation kept'}
