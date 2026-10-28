# SARD 234204 — CWE-122: FULL REPORT

**Полный отчёт pipeline Vishap V5.8.**

---

## Metadata

| Field | Value |
|-------|-------|
| **Session** | `sess-2026-10-12-170032` |
| **audit_id** | `audit-2026-10-12-30d29f` |
| **material_hash** | `sha256:ed77fe831b84c3cac7d37aa7177e70f1697506fff7e69c1e00896ae96641954a` |
| **material_hash_full** | `sha256:ed77fe831b84c3cac7d37aa7177e70f1697506fff7e69c1e00896ae96641954a` |
| **Level** | `D2` |
| **task_type** | `review` |
| **Language** | C |
| **Verdict** | `REQUIRES_REVIEW` |
| **Risk verdict** | `REQUIRES_REVIEW` |

> ⚠️ **Note (v5.8.2):** This report was generated with Vishap 5.8.1, before the fixes.
> Original: `Verdict: SAFE`, `owasp_categories: ['A03:2025 Injection']` — both incorrect.
> Fixed in v5.8.2:
> - `risk_verdict`: 3 levels (EMERGENCY/REQUIRES_REVIEW/SAFE), cwe_ids affects verdict
> - `owasp_categories`: memory safety CWE (122/787/125/129) → 'Memory Safety' (not A03:Injection)
| **cwe_ids** | `['CWE-122', 'CWE-787']` |
| **owasp_categories** | `['Memory Safety']` |
| **provenance_source** | `git/main` |
| **provenance_commit** | `6f3afbf` |

---

## Full Conveyor Output

См. полный отчёт в `PROOF.md` (раздел STONESOUP) и в чат-логе сессии.

**Ключевое из отчёта:**

- CWE-122 — подтверждён
- Корень: `sizeof(pointer)` vs `sizeof(struct)`
- Строка: `data = (twoIntsStruct *)malloc(sizeof(data));`
- CWE-787 — симптом, не корень
- CWE-467 — дополнительный класс
- ABI-оговорка (32/64-bit)

---

## Notes

- Second SARD case study after STONESOUP CWE-129B
- Proves Vishap works on NIST standards
- `material_hash` is 64 hex — real SHA-256