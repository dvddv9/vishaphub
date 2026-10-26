![Vishap](assets/icon.png)

# Vishap Security Analysis

Security analysis for engineering materials — code, specs, logs and configs — inside Claude.
One tool, `vishap_analyze`, sends the material to the Claude API with **your own API key** and
returns a structured Markdown report: CWE-tagged findings, a STRIDE threat model and concrete
fixes.

## What it finds

SQL injection (CWE-89), XSS (CWE-79), command injection / RCE (CWE-78), path traversal
(CWE-22), TOCTOU races (CWE-367), unsafe deserialization, hard-coded secrets and more.

## Requirements

- Python 3.10+ available as `python3` on your PATH. The server uses only the standard library:
  nothing to install.
- An Anthropic API key from <https://console.anthropic.com/settings/keys>.

## Install

```text
/plugin marketplace add dvddv9/vishap
/plugin install vishap-security-bundle@vishap
```

When prompted, enter your **Anthropic API Key** and a **model** (default `claude-sonnet-5-5`).
The key is stored as a sensitive plugin setting.

## Use

> Use vishap_analyze on this file: `db.execute(f"SELECT * FROM users WHERE name = '{name}'")`

### Examples

| Input | Result |
|---|---|
| `db.execute(f"SELECT * FROM users WHERE name = '{name}'")` | Critical SQL injection (CWE-89); fix: parameterized query |
| `<div dangerouslySetInnerHTML={{ __html: user.bio }} />` | Critical XSS (CWE-79); fix: sanitize (DOMPurify) |
| `open(os.path.join("/data", filename)).read()` | High path traversal (CWE-22); fix: `realpath` + allow-list |

Limits: material over 200 000 bytes is rejected (split it); a response cut off at the output
limit is flagged in the report.

## Privacy

- **What leaves your machine:** only the material you pass to `vishap_analyze`, sent to the Anthropic API.
- **Whose key:** yours — entered in the plugin settings and passed to the server as `VISHAP_API_KEY`. The plugin reads no other credential from your environment and ships no key.
- **What is stored:** nothing. No files are written; the report is returned to the chat only.
- **Network:** one HTTPS endpoint, `https://api.anthropic.com/v1/messages`. The URL is fixed in the code.
- **Third parties:** the Anthropic API only. See <https://www.anthropic.com/legal/privacy>.
- **Background activity:** none. The server runs only while Claude is open and does nothing until you call the tool.
- **Safety:** the tool is read-only. Submitted material is treated as data, not instructions.

## Support

Issues: <https://github.com/dvddv9/vishap/issues>

## License

AGPL-3.0-or-later — see [LICENSE](LICENSE).
