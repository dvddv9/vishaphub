# SAST coverage and limits

Vishap's built-in repository scanner is a deterministic rules engine. A language being
recognized means the file is scanned by the matching rules; it does **not** mean that
every vulnerability class has a rule or that the language has semantic taint analysis.

## Current coverage

| Category | Recognized targets | Analysis available |
|---|---|---|
| Programming languages | Python, JavaScript, TypeScript, Java, C, C++, Go, PHP, Ruby, Rust, C#, Kotlin, Swift, Scala | Static rules; Python has AST intrafile taint and bounded interfile taint in repository scans |
| Query and command files | SQL, shell / Bash | Static rules |
| Infrastructure and configuration | Terraform / HCL, YAML, Dockerfile | Static rules |
| Operational data | Logs | Attack-pattern rules, not source-code analysis |

JavaScript's `js_parser.py` contains source/sink patterns, but it is not a general
interfile semantic engine. Other non-Python languages currently receive pattern rules,
not Python-style AST taint. Unknown extensions remain unclassified rather than being
counted as supported.

`vishap scan <directory> --json report.json` records `languages_scanned` and an
`interfile_dataflow` summary. Repository scanning builds context from the bounded set
of Python files; PR diff mode uses the full snapshot for context but only reports
findings whose sink is on a changed line.

## GitHub pull requests

The GitHub App handles `opened`, `reopened`, `synchronize`, and `ready_for_review` pull
request events. It posts a summary comment and a commit status named
`vishap/security`. The status fails when a finding meets the configured threshold
(`VISHAP_GITHUB_FAIL_ON`, default `high`). To block merges, grant the app permission to
write commit statuses and configure `vishap/security` as a required status check in the
repository's branch protection or ruleset. The app cannot change that repository policy
on its own.

## IDE

The `integrations/vscode` extension runs the local `vishap scan` command for the open
workspace and publishes findings as editor diagnostics. It does not upload source code.
It uses the same repository scanner as CI, including interfile Python analysis.

## Comparing accuracy

`tests/bench/compare_sarif.py` scores Vishap, Semgrep, or CodeQL SARIF against the same
106-example labelled corpus. A detection counts as a hit only when CWE and expected
line match exactly (line 0 in the manifest means any line). Extra detections are
counted as unmatched; on labelled-safe files they are false positives. The script
reports precision/recall, safe-file false-positive rate, and per-language counts. It
does not install or run external engines.

Local Vishap result on 2026-11-02, named-file mode: 53 of 71 expected findings hit
(74.65% recall), 17 unmatched detections, precision 75.71%, and findings on 4 of 35
labelled-safe files (11.43%). This is a result on this corpus, not a production rate.
The 402-example blind public corpus remains a separate gate for whether Vishap may say
`SAFE`; it is not a Semgrep or CodeQL comparison.

Example commands from the analyzer directory:

```sh
semgrep scan --config auto --sarif --output semgrep.sarif tests/bench/labelled
python -m tests.bench.compare_sarif --sarif semgrep=semgrep.sarif \
  --covered semgrep=python,javascript,typescript,java,c,cpp,go,php,ruby
```

For CodeQL, create/analyze one database per supported language and pass each SARIF with
its covered-language declaration. For example, Python:

```sh
codeql database create codeql-python --language=python \
  --source-root=tests/bench/labelled --build-mode=none
codeql database analyze codeql-python \
  codeql/python-queries:codeql-suites/python-security-and-quality.qls \
  --format=sarifv2.1.0 --output=codeql-python.sarif
python -m tests.bench.compare_sarif --sarif codeql-python=codeql-python.sarif \
  --covered codeql-python=python
```

Declare only languages actually analyzed. A tool's omission of a declared-language
finding is a miss; an undeclared language is excluded rather than treated as a miss.
The corpus is small and covers only its registered vulnerability classes, so do not
describe a result as an overall vendor ranking.
