# Case Study: Log4Shell — JNDI Injection (CVE-2021-44228)

**Source:** `org.apache.logging.log4j.core.lookup.JndiLookup`
**Language:** Java
**Level:** D3
**Cost:** $0.005721
**Truncated:** No (3050 chars)
**Session:** sess-2026-10-10-143734
**Verdict:** SAFE

---

## Vishap Output

# JndiLookup.java — Log4Shell Surface Analysis

**Level:** D3 | **Session:** sess-2026-10-12-XXXXXX | **Model:** vishap-orchestrator-v5.8
**Flags:** EMERGENCY_INTERRUPT | **Material:** `org.apache.logging.log4j.core.lookup.JndiLookup` (~90 lines, log4j-core)

---

## [ECHO]

Проанализирован `JndiLookup.java` из log4j-core — плагин `StrLookup`, резолвящий JNDI-имена. Вход: `LogEvent event` (не используется), `String key` (JNDI-имя, может быть null). Выход: `String` значение ресурса или `null`. Ключевой путь: `lookup → convertJndiName → JndiManager.getDefaultManager().lookup(jndiName)`. `convertJndiName` добавляет префикс `java:comp/env/` только если строка не начинается с него **и** не содержит `':'`. Любая строка с `':'` проходит без изменений. Это каноническая поверхность **CVE-2021-44228 (Log4Shell)**.

---

## [ROUTE]

stage0 → stage1 (scanner) → stage2 (analyst) → stage4 (synthesizer) → **stage5 (transmitter)**.
stage3 отсутствует в route. `force_emergency: true` из stage4 → режим EMERGENCY. `return_to_stage2/3: false`. `stop_reason: risk`.

---

## [CONCLUSION]

`JndiLookup` принимает недоверенный `key` и передаёт его в JNDI-резолвинг без allowlist схем. `convertJndiName` реализует **colon detection**, а не **scheme detection** — любая строка с `':'` (например `ldap://attacker/x`) проходит без префикса и попадает в `JndiManager.lookup`. Это RCE-поверхность Log4Shell. Немедленное действие: нейтрализовать `JndiLookup` (JVM-флаги + `log4j2.disable.jndi=true` или апгрейд до 2.17.1+), затем ввести allowlist схем.

---

## [RISK_NODES]

| # | Узел | Приоритет | Суть |
|---|------|-----------|------|
| 1 | Неявное допущение | критично | Предполагается allowlist в `JndiManager` — в файле не подтверждено |
| 2 | Слабое обобщение | критично | `':'` трактуется как схема; любая строка с `':'` проходит |
| 6 | Стратегическое избегание | критично | Валидация делегирована `JndiManager` без контракта |
| 4 | Сдвиг тезиса | важно | Javadoc обещает scheme detection, код делает colon detection |
| 5 | Внутреннее противоречие | важно | Контракт метода ≠ тело метода |
| 7 | Производительность | важно | Новый `JndiManager` на каждый lookup |
| 8 | Надёжность | важно | Ловится только `NamingException`; silent failure |
| 9 | Масштабируемость | важно | Блокирующий I/O на горячем пути логирования |
| 11 | Ломающие изменения | важно | Allowlist схем ломает `ldap:`/`rmi:` конфигурации |
| 3 | Конкурирующая реализация | опционально | Вне слайса |
| 10 | Конкурентность | опционально | Зависит от `JndiManager` |

---

## [THREAT_MODEL]

**Компоненты:** `JndiLookup`, `JndiManager` (внешний, security-critical), `StatusLogger`, plugin framework, внешний JNDI-провайдер (LDAP/RMI/DNS).

**Trust boundaries:**
- **TB-1:** log event / lookup expression → `JndiLookup.lookup` (недоверенный вход)
- **TB-2:** `JndiLookup` → `JndiManager` → внешний JNDI-провайдер (network egress)
- **TB-3:** `JndiLookup` → `StatusLogger` (логирование)

**Threats (STRIDE):**

| STRIDE | Граница | Угроза | Приоритет |
|--------|---------|--------|-----------|
| E | TB-2 | RCE через удалённый JNDI-провайдер (Log4Shell) | критично |
| S | TB-1 | Подмена ключа на `ldap://attacker/...` | критично |
| T | TB-1 | Ключ не валидируется на схему | критично |
| D | TB-2 | DoS: блокирующий lookup на горячем пути | важно |
| R | TB-3 | Нет audit-лога подозрительных lookup-ов | важно |
| I | TB-3 | Утечка resolved value (секрета) в логи | важно |

**Итого:** 6 угроз — 3 критично, 3 важно. **Top-3:** E (RCE), S/T (невалидированный ключ), D (DoS).

---

## [SILENCE_LAYERS]

- **Input silence:** происхождение и доверенность `key` не указаны. Javadoc: `event ... is ignored`. Невозможно оценить, контролируется ли ключ атакующим.
- **Assumption silence:** предполагается allowlist в `JndiManager.getDefaultManager()` — в файле не подтверждено, контракт неявный.
- **Consequence silence:** RCE — необратимое последствие (выполнение произвольного кода). Владельцы приложений с log4j-core несут риск.

---

## [INTERSECTION_RISKS]

1. **Lookup logic × JndiManager:** `convertJndiName` пропускает `':'` → `JndiManager` резолвит произвольную схему. Композиция двух «нейтральных» компонентов даёт RCE-поверхность.
2. **Logging path × Network I/O:** блокирующий JNDI-вызов внутри пути логирования → деградация приложения при медленном внешнем сервисе (DoS).
3. **Silent failure × Security monitoring:** `NamingException → warn → null` — атаки неотличимы от обычных сбоев, SIEM не получает сигнала.

---

## [ASSEMBLY]

**Иерархия:**
- **Core:** `lookup` (точка входа, недоверенный key) → `convertJndiName` (scheme-agnostic, критично) → `jndiManager.lookup` (point of no return)
- **Service:** `JndiManager.getDefaultManager` (фабрика), `StatusLogger` + Marker `LOOKUP`, `AbstractLookup`/`StrLookup`
- **Infra:** plugin framework, JVM JNDI-провайдеры (`com.sun.jndi.*`), внешние JNDI-таргеты, сетевой egress

**Critical path:** `untrusted key → convertJndiName → JndiManager.lookup → external provider → RCE`

**Connections:** TB-1 (untrusted-input) → internal-call → passthrough (scheme-agnostic) → network-egress (TB-2) → log (TB-3).

---

## [REFACTORING]

**Вариант A — Hard-disable JndiLookup.** Удалить/заблокировать плагин или `log4j2.disable.jndi=true`. Мгновенно закрывает RCE, нулевая стоимость, обратимо. Минус: ломает легитимные JNDI-конфигурации.

**Вариант B — Allowlist схем + JVM hardening + upgrade.** Ограничить `convertJndiName` только `java:comp/env/`, отключить удалённые JNDI-провайдеры, обновить до 2.17.1+. Сохраняет функциональность, многослойная защита. Минус: breaking change, координация релиза.

**Вариант C — Replace JndiLookup на safe lookup.** Убрать JNDI-резолвинг из пути логирования, оставить только env/properties. Устраняет класс уязвимости, убирает блокирующий I/O. Минус: наибольший объём, миграция конфигураций.

**Рекомендация:** A немедленно (JVM-флаги без релиза) → B как долгосрочное решение.

---

## [PARALLELS]

- **CVE-2021-44228 (Log4Shell):** исходная RCE через `${jndi:ldap://...}`.
- **CVE-2021-45046:** DoS/обход после первого патча.
- **CVE-2021-45105:** DoS через рекурсивные lookup-ы.
- **CVE-2021-44832:** RCE через JDBC appender (смежная поверхность).
- **Аналогия:** любой «lookup по внешнему ключу без allowlist» — Spring SpEL injection, OGNL (Struts), EL injection.

---

## [TESTS]

Тесты в слайсе отсутствуют. **Edge cases для `convertJndiName`:**
- `key == null` → `null`
- `key == ""` → префикс + `""`
- `key == ":"` → проходит без префикса (схема пустая)
- `key == "ldap://attacker/x"` → проходит без префикса (**RCE-вектор**)
- `key == "java:comp/env/foo"` → без изменений
- `key == "a:b:c"` → проходит без префикса
- `NamingException` path → `warn` + `null`

**Рекомендуемые тесты:** unit на `convertJndiName` (все edge cases), integration на отказ `ldap:`/`rmi:`/`dns:` после allowlist, security-тест на `${jndi:ldap://...}` в лог-сообщении.

---

## [ACTION]

**NOW (без релиза):**
1. Применить JVM-флаги: `com.sun.jndi.ldap.object.trustURLCodebase=false`, `com.sun.jndi.rmi.object.trustURLCodebase=false`, `com.sun.jndi.cosnaming.object.trustURLCodebase=false`.
2. Если JNDI lookup не нужен — `log4j2.disable.jndi=true`.
3. Инвентаризация: какие сервисы используют `JndiLookup`.

**TODAY:**
4. Обновить log4j-core до 2.17.1+.
5. Проверить конфигурации на `ldap:`/`rmi:`/`dns:` в lookup-ах.

**TOMORROW:**
6. Ввести allowlist схем в `convertJndiName` (вариант B).
7. Добавить audit-логирование подозрительных схем + метрику `NamingException`.

**LATER:**
8. Timeout + circuit breaker на уровне `JndiManager`.
9. Рассмотреть вариант C (полная замена) как долгосрочное решение.

---

## [QUESTIONS]

1. Какая версия log4j-core в манифесте? (VERIFY)
2. Применяет ли `JndiManager.getDefaultManager()` allowlist схем? (VERIFY — исходники `JndiManager`)
3. Потокобезопасен ли `JndiManager.getDefaultManager()`? (VERIFY)
4. Есть ли легитимные `ldap:`/`rmi:` конфигурации в парке? (VERIFY)
5. Контролируется ли `key` атакующим через лог-сообщение в вашем приложении?

---

## [FUNC:FULL]

**ECON:** effort ~2–4h (JVM-флаги + инвентаризация) + ~1–2 дня (апгрейд + allowlist), cost $0 (библиотечный патч), ROI критически высокий (предотвращение RCE), budget $0, cloud delta $0, cost of delay — необратимый RCE при эксплуатации.

**FAIL:** критично — `jndiManager.lookup(jndiName)` с невалидированным ключом → RCE; `convertJndiName` пропускает любую строку с `':'`; cascade: untrusted key → JNDI resolution → class loading → RCE; recovery: апгрейд + JVM-флаги + allowlist, откат версии технически возможен, но не рекомендуется из-за CVE.

**METRICS:** ~90 строк (вкл. ASF license), ~40 строк кода, 2 метода, 11 зависимостей, 0 тестов в слайсе, branches=3, nesting_max=2, resilience_score=2/10, coupling=moderate, cohesion=high.

**ALTERNATIVES:** A — hard-disable (мгновенно, $0, low risk); B — allowlist + JVM hardening + upgrade (medium risk, сохраняет функциональность); C — replace на safe lookup (medium risk, устраняет класс уязвимости); языки/фреймворки/БД — N/A (библиотечный класс).

**EVOLVE:** coupling=4/10 (статический `JndiManager.getDefaultManager()`), abstractions=5/10, feature_add=4/10, module_replace=6/10, overall=4/10; friction — статическая фабрика затрудняет тестирование и подмену.

**COMPARE:** A — time ~2h, cost $0, risk low, complexity low; B — time ~1–2 дня, cost $0, risk medium, complexity medium; C — time ~1–2 недели, cost $0, risk medium, complexity high.

---

## [MANDATORY BASE]

1. **ECONOMICS:** time ~2–4h (немедленно) + ~1–2 дня (полное решение), cost $0, при условии библиотечного патча без изменения облачных ресурсов.
2. **RISKS:** критично — RCE через JNDI (Log4Shell); важно — DoS через блокирующий lookup, silent failure; при условии, что `key` контролируется атакующим.
3. **INFRASTRUCTURE:** pool_size=N/A (библиотечный класс, `JndiManager` создаётся per-lookup), при условии отсутствия серверного компонента.
4. **CODE:** change ~40 строк (`convertJndiName` + audit), при условии введения allowlist схем.
5. **ACTION:** now — JVM-флаги + инвентаризация; tomorrow — апгрейд + allowlist.
6. **TIMELINE:** NOW — JVM-флаги; TODAY — апгрейд log4j-core; TOMORROW — allowlist схем; LATER — timeout + circuit breaker.
7. **PRODUCTION IMPACT:** users N (все сервисы с log4j-core), deploy window — немедленно для JVM-флагов, rollback N min (откат флагов тривиален; откат версии не рекомендуется).
8. **SLO IMPACT:** current N% (SLO не определены), after N% (не изменится при корректном апгрейде), при условии отсутствия легитимных `ldap:`/`rmi:` конфигураций.
9. **CLOUD COST:** current $0, projected $0, delta ±$0 (библиотечный патч, без изменения облачных ресурсов).
10. **ON-CALL:** new alerts — всплеск `NamingException` (>10/min), подозрительные схемы (>0); runbook — нейтрализация JndiLookup + апгрейд; escalation — security team при обнаружении `ldap:`/`rmi:` в логах.

---

## [REFLEXION]

1. **Слабое место:** `JndiManager` — чёрный ящик, allowlist не подтверждён → **исправлено:** зафиксировано как VERIFY-флаг, критичность выведена из допущения об отсутствии allowlist (консервативная оценка).
2. **Слабое место:** stage3 отсутствует в route → **исправлено:** отмечено в [ROUTE], анализ построен на stage1/2/4 без пробелов в обязательных блоках.
3. **Слабое место:** `force_emergency: true` мог быть проигнорирован → **исправлено:** режим EMERGENCY активирован, [ACTION] начинается с немедленных шагов без релиза.

**Итог:** accepted

---

*Audit trail добавляется pipeline'ом (orchestrator.py) автоматически.*

[AUDIT_TRAIL]
audit_id: audit-2026-10-10-115968
material_hash: sha256:b7133238f645a5e2bef6b7d217bd9b64507f4346820ccacfa5dd9a8cd408f007
pii_detected: false
compliance_flags: []
critique_verdict: SAFE


[COMPLETENESS]
level: D3
required: 12
missing: []
loss_pct: 0.0%
verdict: ACCEPTABLE

---

## Reproduce

    vishap analyze data/real_cases/hard/log4shell_JndiLookup.java
