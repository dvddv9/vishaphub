# Hard Case Studies

5 production-grade open-source files analyzed by Vishap V5.8.
All files are truncated to 12,000 chars by pipeline design — Vishap
reports loss_pct honestly in [Completeness].

## Summary

| # | Project | Lang | Level | Truncate | Cost | Key findings |
|---|---------|------|-------|----------|------|--------------|
| 1 | [Log4Shell](log4shell-jndi-lookup.md) | Java | D3 | No | $0.0057 | CVE-2021-44228, JNDI injection |
| 2 | [OpenSSL EVP](openssl-evp-enc.md) | C | D3 | 75% | $0.0092 | CVE-2023-5363, race, partial-init UB |
| 3 | [Redis networking](redis-networking.md) | C | D4 | 95% | $0.0071 | TOCTOU auth, io-thread race, UB |
| 4 | [K8s scheduler](k8s-scheduler.md) | Go | D4 | 50% | $0.0080 | Irreversible `metrics.Register()`, shared state |
| 5 | [PostgreSQL execMain](postgres-execmain.md) | C | D4 | 88% | $0.0088 | Snapshot leak, privilege escalation via hook |

**Total:** 5 analyses, ~$0.0388. Average: $0.0078.

## Languages covered

- Java (1)
- C (3)
- Go (1)

## Levels

- D3: 2 cases
- D4: 3 cases

## Notable

- **CVE detection:** Vishap identified CVE-2021-44228 (Log4Shell) and CVE-2023-5363 (OpenSSL) directly from code.
- **Truncate resilience:** Redis 250 KB -> 12 KB (95% loss) — Conveyor honestly reported `loss_pct=0.0%` for stage-visible slice, and PostgreSQL `loss_pct=16.7%, missing=5`.
- **No false emergency stops:** after the `llm_emergency_downgraded` gate, security-sensitive code is analyzed, not skipped.

## Reproduce

    vishap analyze data/real_cases/hard/log4shell_JndiLookup.java
    vishap analyze data/real_cases/hard/openssl_evp_enc.c
    vishap analyze data/real_cases/hard/redis_networking.c
    vishap analyze data/real_cases/hard/k8s_scheduler.go
    vishap analyze data/real_cases/hard/postgres_execMain.c
