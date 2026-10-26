# Vishap Claude (Bundle)

Security analysis for engineering materials (code, spec, logs, config) via Claude API (Anthropic SDK).

## What it does

Detects SQL injection (CWE-89), XSS (CWE-79), RCE (CWE-78), TOCTOU (CWE-367), path traversal (CWE-22), command injection (CWE-78).
Returns a structured Markdown report with CWE, STRIDE threat model, and recommendations.

## Install

```bash
pip install -r requirements.txt
```

## Usage

1. Install the plugin in Claude Desktop.
2. Configure:
   - **Anthropic API Key** = `sk-ant-...` (from https://console.anthropic.com/settings/keys)
   - **ANTHROPIC_MODEL** = `claude-sonnet-5-5` (or another model)
3. Ask Claude:
   > Use vishap-analyze to analyze: `db.execute(f"SELECT * FROM users WHERE name = '{name}'")`

## Examples

### 1. SQL injection (CWE-89)

Input:
```python
db.execute(f"SELECT * FROM users WHERE name = '{name}'")
```
Output: Critical SQL injection — `' OR '1'='1` returns all users. Fix: parameterized query.

### 2. XSS (CWE-79)

Input:
```jsx
<div dangerouslySetInnerHTML={{ __html: user.bio }} />
```
Output: Critical XSS — arbitrary JS execution. Fix: sanitize with DOMPurify.

### 3. Path traversal (CWE-22)

Input:
```python
open(os.path.join("/data", filename)).read()
```
Output: High — `../etc/passwd` reads arbitrary files. Fix: `os.path.realpath` + allowlist.

## Privacy

- **What leaves your machine:** the material you submit is sent to the Anthropic API (Claude) for analysis.
- **Whose key:** **your** Anthropic API key, entered in the plugin settings (`userConfig`) and passed to the server as `VISHAP_API_KEY`. The plugin does not read any credential from your environment. The key is stored in Claude Code config (sensitive), never in the plugin repo.
- **What is stored:** no material is stored by the plugin itself. Responses are returned to Claude Code only.
- **Third parties:** Anthropic API (Claude). No other services.
- **Retention:** none on the plugin side; Anthropic API retention follows Anthropic policies (see https://www.anthropic.com/legal/privacy).
- **Background actions:** none. The plugin only runs when you call `vishap_analyze`.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).

## Install

```bash
/plugin marketplace add dvddv9/vishap
/plugin install vishap-security-bundle@vishap
```
