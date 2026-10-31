# Changelog

All notable changes to VishapHub. Format based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Fixed

- **The page lost its style and script when the hub was installed with pip, pipx or the Windows installer.** `package-data` listed the page and the greeting but not `styles.css`, `app.js` or `favicon.svg`, so those were 404 outside the source tree (the Docker image runs from the tree and was not affected). They are listed now, and a test fails if the server serves a file the package leaves out.

### Fixed (continued)

- **A DeepSeek key typed in the page was sent to Anthropic and rejected.** The page now has a provider choice (Anthropic or DeepSeek) next to the key field. It sends a preset *name*; the addresses are fixed in the code, and a custom `VISHAP_HUB_LLM_URL` is never overridden. The operator's own key is not used for a provider the operator did not choose.
- The run page's JSON, SARIF and Markdown links download the file instead of showing it; the page's «↓ json» button works again after a reload (the last result is kept for the tab).
- The reason «the model saw danger the rules did not» was shown whenever the model's verdict was higher than the rules', even if both saw the same findings. It now says what is true: the model rated the risk higher, with both verdicts.
- Analyser: `cmd-injection-py` no longer fires on `subprocess.run([...])` with an argument list (`shell=True` is still caught by `shell-true`).

### Added

- **DeepSeek** as a provider: `VISHAP_HUB_LLM_PROVIDER=deepseek`, `vishap-hub init --provider deepseek`, and a CLI `--provider` on `run`.

- **An external scanner's SARIF as a third reader.** `/run` takes an optional `sarif`. Its findings join the hub's
  own where they name the same class near the same line, stay where nothing else saw them, and a lone one raises the
  verdict to `REQUIRES_REVIEW`. It never lowers a verdict and never drops a finding. The fingerprint records the
  findings only when they were sent.
- **A person's note on a finding.** `POST /api/runs/<id>/accept` and `/unaccept`: who, when and a reason, kept in
  the run's own result (no migration) and shown beside the finding. The verdict is not touched. In a team the
  creator (`run.accept.own`) or an owner (`run.accept.any`) may; the audit row holds the finding, not the reason.
- **Standing rules.** `/run` takes an optional `accept_rules`: findings like this are noted as accepted, for this
  reason. They write notes, never exclusions.
- **Findings more than one reader saw come first** in the report and in the page.
- **Self-hosting.** `selfhost/`: a Docker Compose bundle (solo, or `--profile team` with Postgres and migration) with
  `install.sh` / `install.ps1`, `vishap.sh` / `vishap.ps1` (status, logs, backup, restore, upgrade), a pipx installer, and
  a per-user Windows installer that carries its own Python (`selfhost/windows/build.ps1`). `vishap-hub init`, `doctor`
  and `serve` set up and run it on one machine from a settings file (`~/.vishaphub/config.env`). See `docs/self-hosted.md`.
- **Any model.** `VISHAP_HUB_LLM_PROVIDER` = `anthropic`, `openai` (OpenAI, OpenRouter, Ollama, LM Studio, vLLM: any server
  with the OpenAI chat API; `VISHAP_HUB_LLM_URL`, `VISHAP_HUB_LLM_MODEL`) or `none` (rules and validator only). The key is
  optional for a server on this machine. Redaction, the meter and the error scrubbing are unchanged.
- **Offline mode.** `VISHAP_HUB_OFFLINE=1` refuses connections outside this machine and the private network
  (`VISHAP_HUB_ALLOWED_HOSTS` adds hosts) and turns the voice off; `VISHAP_HUB_VOICE=0` turns it off alone.
- **The installer chooses how submitted code runs.** `VISHAP_HUB_ISOLATION` = `auto` (as before), `docker` (only in a worker
  container) or `host` (on this machine, for code you trust; the result says `isolation: host, confirmed: false`). An
  unknown value runs nothing. `validator.safe.refusal` and `validate` take `host_ok`.

### Fixed

- The hub image's `/data` is writable by the non-root user, so a mounted volume can hold the runs.
- The report and the page named every two-reader finding "rules + model"; they now name the readers that saw it.

## [0.5.0] - 2026-10-31

### Added

- **Opt-in checked fix loop.** Send `"verify_fix": true` to `/run` or `/run/stream` to check the model's patch,
  feed a rejected or partial result back with its reason, and try at most twice more. The result is the best
  patch that the hub checked; the model cannot lower the risk verdict. The loop stops without retry when checks
  cannot be run. Each retry is an additional model call.
- **Evidence for each fix attempt.** The result fingerprint records the patch hash, files, status and reason for
  every attempt, plus why the loop stopped.
- **Review mode.** Material with a question can be sent to the model while the rules check it. The stricter
  verdict wins; without a model key the result says the question was not sent to a model.
- **Findings from two readers are joined.** Findings for the same class of defect near the same line carry
  `seen_by`; the report shows what each reader found alone and what both found.

### Changed

- **A lighter image: 1.06 GB to 264 MB, build 221 s to 78 s.** The hub no longer installs the analyser's unused
  dependency set or a compiler. It installs pinned `pytest`, `edge-tts` and `psycopg[binary]` requirements; the
  `.dockerignore` excludes `.git`, caches and `.env` files from the build context.
- **Safer request handling.** A 30-second read timeout and a cap of four concurrent runs protect HTTP threads;
  malformed content lengths return `400`, and an unhandled run error returns `500` without exposing exception
  text to the client.
- **Validator isolation.** Submitted tests get a clean environment. Strict execution requires a confirmed network
  namespace or worker container; skipped-only test runs do not count as a pass. A Python socket guard is not
  reported as process-level isolation.
- **Reports.** The model's summary and patch are separated from the rules' findings. The report says whether the
  hub ran the proposed patch and links a possible overlap between model and rules findings.
- **Documentation.** The README includes the small open-scanner comparison and its limits. `SECURITY.md` and
  `docs/privacy.md` describe the current data paths, storage, retention and team isolation.

### Security

- **Trusted proxy settings.** Render configures `X-Forwarded-For` and one trusted hop. Check the selected address
  through `/api/team/diagnostics` before claiming per-visitor limits publicly.
- **Team data boundary.** Query filters and Postgres row-level security scope `runs`, `audit_log` and `usage` to
  the active team for the restricted `vishap_hub_app` role. CI exercises the integration tests against Postgres.

### Fixed

- Findings carry their message, CWE and fix; `REQUIRES_REVIEW` reports its own meaning instead of the definition
  for `SAFE`.

## [0.4.0] — 2026-10-30

### Added

- **Team mode.** Owners, roles, per-team retention, delete and an audit trail; runs and teams
  in Postgres, isolation covered by tests. Admin entry point: `python -m hub.admin`.
- **Spend control.** Per-team and per-user quotas; a process-wide budget for runs and
  characters that survives restarts; alerts on threshold; measured tokens kept apart from
  estimates (`meter.py`).
- **A budget of its own for the chat.** Anonymous messages that reach a model spend
  `VISHAP_HUB_GLOBAL_CHATS_PER_DAY` / `VISHAP_HUB_GLOBAL_CHAT_CHARS_PER_DAY`, not the run
  budget: a conversation on the site cannot close the door for runs.
- **SARIF export.** `GET /api/runs/<id>.sarif` returns SARIF 2.1.0, written by the analyser's
  own writer. Owner check identical to the report itself; `501` when the analyser is absent.
- **Redaction before the model.** `proposal._call` passes the material through
  `src.tools.redact` before it leaves; counts by category come back with the answer.

### Security

- **Owner on every run.** Without a token `403`; for somebody else's run `404`, so existence is not confirmed.
  `/api/runs`, `/r/<id>`, `/api/runs/<id>` and the SARIF export share the check.
- `API_KEY_PEPPER` in the analyser is refused at startup when it is still a placeholder and tenant keys are on.

### Known gaps at the 0.4.0 release

- Card numbers were not redacted at that release.
- Hub row-level security had not yet been documented as independently verified at that release.
- Runs lived in memory (200 last, until restart) unless the file mirror or Postgres was set.
