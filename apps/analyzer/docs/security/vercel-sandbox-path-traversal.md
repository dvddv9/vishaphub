# Path handling in `vercel/sandbox`: what `normalizePath` actually does

**Status:** analysis of client-side code, no exploit demonstrated against the
service. Written for a HackerOne draft; read the "What is *not* established"
section before filing anything.

**Asset:** `vercel/sandbox` npm package / Sandbox API
**Version analysed:** repository snapshot in `sandbox/` (package
`@vercel/sandbox`)
**CWE:** CWE-22 (path traversal) — *conditional*, see below

## Code path

1. `writeFiles()` in `packages/vercel-sandbox/src/api-client/api-client.ts:871`
   iterates over the caller's files and computes the archive entry name with
   `normalizePath({filePath: file.path, extractDir, cwd})` (line 873).
2. `normalizePath()` in `packages/vercel-sandbox/src/utils/normalizePath.ts:15`
   resolves the path against `cwd` (or normalises an absolute input) and returns
   `path.posix.relative(extractDir, basePath)`.
3. `FileWriter.addFile()` in `.../api-client/file-writer.ts:65` passes that name
   into `tar-stream`'s `pack.entry({name: ...})` — **verbatim, with no
   validation**.
4. The gzipped tarball is POSTed to the Sandbox API together with `extractDir`.

So the client side has no `..` filter, and the archive entry name is whatever
`relative()` produced. That part of the original report is correct.

## What the code does with `..`

`normalizePath` does **not** reject `..`; it folds it away against `cwd` and then
re-anchors the result at `extractDir`:

| declared path | cwd | extractDir | archive entry |
| --- | --- | --- | --- |
| `../../etc/passwd` | `/vercel/sandbox` | `/` | `etc/passwd` |
| `/etc/passwd` | `/bar` | `/` | `etc/passwd` |
| `bar.txt` | `/` | `/vercel` | `../bar.txt` |

Reproduced by `scripts/poc_path_traversal.py` (mock: builds a real gzipped tar
with `tarfile`, never contacts the API) and pinned by
`tests/test_normalize_path.py`, which also reproduces every case the upstream
`normalizePath.test.ts` asserts, so the port cannot drift.

## What is *not* established

**The chain in the original report does not follow.** For
`writeFile("../../etc/passwd")` the entry name is `etc/passwd`:

- it carries no `..` component, so nothing in the archive is traversal-shaped;
- it is relative, so it cannot overwrite an absolute host path by itself;
- `extractDir` is `/` in that example, which is the **sandbox root**, not the
  host filesystem. Extracting `etc/passwd` there produces `/etc/passwd` *inside
  the sandbox*.

That is by design: the client's job is to produce names relative to
`extractDir`, and it does.

## What is worth reporting

One shape does put `..` into the archive: when `extractDir` is **not an ancestor**
of the resolved path, `path.relative()` returns a `..`-prefixed name. That case is
in the upstream test suite, marked:

```ts
// TODO: Should this be allowed?
expect(normalizePath({ filePath: "bar.txt", cwd: "/", extractDir: "/vercel" }))
  .toBe("../bar.txt");
```

So the maintainers have already noticed it. It becomes a vulnerability only if
the server-side extractor does not reject entries containing `..` or absolute
components — which cannot be observed from this repository.

Impact if the server is permissive: a caller who controls `cwd`/`extractDir`
(they are caller-supplied arguments) can place a file outside `extractDir`
within the sandbox, e.g. into `/etc` or `/usr/local/bin` of the sandbox VM. That
is still *inside a disposable sandbox*, so the severity depends entirely on
whether the sandbox is expected to confine writes to `cwd`, and on whether
anything in that image runs privileged.

## Suggested remediation (client-side, cheap)

`normalizePath` should assert the invariant its documentation implies:

```ts
const rel = path.posix.relative(params.extractDir, basePath);
if (rel === "" || rel.startsWith(".." + path.posix.sep) || rel === ".." ||
    path.posix.isAbsolute(rel)) {
  throw new Error(`path escapes extractDir: ${params.filePath}`);
}
return rel;
```

That would turn the `../bar.txt` case into an explicit error instead of an
archive entry, and removes the need to trust the server's extractor.

Server-side, an extractor that rejects `..` and absolute entry names is the
correct defence regardless of the client.

## How to verify the remaining question

Register a test tenant with the Sandbox API and call `writeFiles` with

```ts
// cwd and extractDir chosen so that relative() must emit ".."
files: [{ path: "bar.txt", content: "x" }],
cwd: "/",
extractDir: "/vercel",
```

then check (a) whether the request is rejected, and (b) if not, where the file
lands inside the sandbox — `readFile("../bar.txt")` or a listing of `/` settles
it. That is a permitted, non-destructive test on your own account; it was **not**
performed here.

## Summary

- Client does not validate paths, and `FileWriter` trusts the name: **true**.
- `writeFile("../../etc/passwd")` writes the host's `/etc/passwd`: **not
  reproduced** — the entry is `etc/passwd`, relative to the sandbox root.
- A `..` entry can reach the archive when `extractDir` is not an ancestor:
  **true**, and known upstream ("TODO" comment).
- Whether that is exploitable: **unknown without testing the service**.

Suggested severity if the server accepts such entries: **Low–Medium** (requires
the caller to choose their own `cwd`/`extractDir`, and stays inside the sandbox).
Informational otherwise.
