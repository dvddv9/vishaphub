# Security Policy

vishap-generator turns a spec into code by calling a language model, then runs that code to check it.
Both facts are the risk. This is what is protected, what is not, and how to report a problem.

**Version 0.7.0**

## Threat model

| Asset | Boundary | Threat |
|---|---|---|
| Spec text | user -> model provider | The spec leaves the machine unless the endpoint is local (Ollama). It may hold secrets or personal data: do not put them in a spec. |
| Model key (`CUSTOM_LLM_KEY`) | environment -> process | Leak through git, logs, error text, or a web page that spends it. |
| Generated code | model -> Verify | The code is written by a model and executed by Verify. It may be wrong or hostile. |
| Output folder | Deliver -> disk | Writing outside `--out`, overwriting files by accident. |
| Web form and API | browser -> server | Another site using your browser to reach the server; anyone on the network when the server is not loopback. |

## What is implemented

1. **The key stays out of everything.** It is read from the environment only; it is replaced by `[key]` in error text (`llm/_scrub.py`), is not in a `repr`, and is never written to a trace, a log or a response. Keys sent by the browser live for one request and are not stored.
2. **Plain http only for localhost.** A key never crosses the network unencrypted. There is no default URL: a forgotten variable cannot send a spec to a provider nobody chose.
3. **Secrets are cut out before the model.** `tools/redact.py` replaces API keys, tokens, private keys, JWTs and passwords (in URLs and in `password = ...`) with `[REDACTED:<kind>]` in the spec text, requirements and problem lines. It catches the common shapes only: do not rely on it to make a spec with secrets safe. The trace records counts, never values.
3. **Data is not instructions.** Spec text and tool output reach the model between random `VG_<LABEL>_<hex>` markers (`pipeline/prompts.py`), new on every call, so the text cannot close the block.
4. **Writes stay inside `--out`.** Absolute paths, `..` and symlinks are rejected; a failure in the middle cancels the whole run and `rollback` restores the previous files (it refuses if a file changed since).
5. **The gate** blocks writing when something is not proven (see README). `--force` is explicit and is recorded in the trace as `forced: true`.
6. **Server.** Loopback by default; any other host needs `GENERATOR_API_TOKEN`. JSON bodies only, Host and Origin must match, 256 KB body limit, one generate run at a time (429), a request limit per client address (`GENERATOR_RATE_LIMIT`, `Retry-After`), job ids are random 128-bit values, `GET /api/jobs/<id>` needs the token when one is set. Logs hold method, path, status and ids, never a body or a key (a filter removes the configured key from every record). The browser picks a model provider from the server's allow-list and cannot name a URL. The API runs Deliver as a dry run into an empty temporary folder: it never reads or writes the server's disk.

## What is NOT protected

- **Verify does not isolate generated code.** It runs as a child process with the user's rights: cleaned environment (no keys), a temporary folder, a timeout, `-X utf8`. That checks the work of a cooperative model; it does not stop hostile code. Use the Docker image (`deploy/README.md`) or a similar jail before you take specs from other people. The Docker files are written but have not been run in this repository's tests.
- The Vishap analyzer, when used, reads the generated code with its own model and its own key.
- No accounts, quotas or audit log on the server: it is a tool for one person or one team.

## Reporting

This is a local project without a public tracker yet. Tell the maintainer directly (hndav9@yahoo.com). Do not post a working exploit or a real key in an issue.
