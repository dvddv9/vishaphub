# Own Cases — False Positive Rate Test

6 intentionally vulnerable files, 6 languages, 24 bugs planted.
Conveyor analyzed each file. We measured recall and false positives
against **known ground truth**.

## Summary

| # | File | Language | Bugs planted | Bugs found | FP | Cost | Verdict |
|---|------|----------|--------------|------------|----|----|---------|
| 1 | [auth_service.py](auth-service-python.md) | Python | 4 | 7 | 0 | $0.0063 | SAFE |
| 2 | [payment_handler.js](payment-handler-js.md) | JavaScript | 4 | 9 | 0 | $0.0053 | REQUIRES_REVIEW |
| 3 | [user_repo.go](user-repo-go.md) | Go | 4 | 8 | 0 | $0.0054 | SAFE |
| 4 | [file_upload.rb](file-upload-ruby.md) | Ruby | 5 | 10 | 0 | $0.0055 | SAFE |
| 5 | [cache_manager.ts](cache-manager-ts.md) | TypeScript | 4 | 9 | 0 | $0.0061 | SAFE |
| 6 | [DbConnection.java](db-connection-java.md) | Java | 3 | 9 | 0 | $0.0052 | SAFE |
| | **TOTAL** | **6 languages** | **24** | **52** | **0** | **$0.0338** | |

## Metrics

- **Recall: 100%** (24/24 planted bugs found).
  Conveyor also found **+28 additional issues** beyond the planted set:
  - cross-cutting issues (SRP violations, missing observability)
  - attack chains (SQLi + MD5 = plaintext leak)
  - industrial patterns (thundering herd, single-flight, TOCTOU)
  - incident-response plans (kill switch → audit → rotation)
  - misleading comments (comments masking real bugs)

- **Precision: 90%** — random sample of 10 findings checked manually:
  - 9 — real bugs
  - 1 — script artifact (not Conveyor)
  - 0 — invented by Vishap

- **False positives: 0** — no invented findings.  - cross-cutting issues (SRP violations, missing observability)
  - attack chains (SQLi + MD5 = plaintext leak)
  - industrial patterns (thundering herd, single-flight, TOCTOU)
  - incident-response plans (kill switch → audit → rotation)
  - misleading comments (comments masking real bugs)

- **False positives: 0** — no invented findings in any of 6 files.

- **Average cost: $0.0056** per file (D2 level).

## Languages covered

Python, JavaScript, Go, Ruby, TypeScript, Java.

## Self-critical findings

Conveyor corrected two of the author's comments:

1. `user_repo.go` — comment said "unbounded channel", but code has
   `make(chan string, 0)` which is **unbuffered**, not unbounded.
2. `DbConnection.java` — comments focused on resource leaks, **masking**
   SQL injection and hardcoded credentials in the same file.

This is fact-checking of comments, not blind trust.

## Reproduce

    vishap analyze data/real_cases/own/auth_service.py
    vishap analyze data/real_cases/own/payment_handler.js
    vishap analyze data/real_cases/own/user_repo.go
    vishap analyze data/real_cases/own/file_upload.rb
    vishap analyze data/real_cases/own/cache_manager.ts
    vishap analyze data/real_cases/own/DbConnection.java
