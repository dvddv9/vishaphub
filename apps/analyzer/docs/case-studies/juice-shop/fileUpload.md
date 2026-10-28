\# Juice Shop fileUpload.ts — 3 critical vulnerabilities



\*\*File:\*\* routes/fileUpload.ts (6.1 KB)

\*\*Cost:\*\* \~$0.007

\*\*Time:\*\* \~60 sec



\## Found



1\. \*\*Zip-slip (CRITICAL)\*\* — `path.resolve('uploads/complaints/' + entry.path)`

&#x20;  + `fs.createWriteStream` → arbitrary file write.

&#x20;  Guard: `absolutePath.includes(path.resolve('.'))` — substring check, not canonical prefix.



2\. \*\*XXE file disclosure (CRITICAL)\*\* — `parseXmlString(data)` without disabling

&#x20;  external entities → system file read + exfiltration via reflected error.



3\. \*\*Unsafe YAML deserialization (CRITICAL)\*\* — `yaml.load` inside

&#x20;  `vm.runInContext`. `vm` is \*\*not\*\* a security boundary (Node.js docs).



\## Also found



\- `checkFileType`: no optional chain → TypeError → 500 instead of 400.

\- No size limit before `unzipper.Open.buffer` → zip bombs.

\- Race condition on shared challenge state.

\- Duplicated error-classification between XML and YAML handlers.



\## Why this matters



`npm audit` finds CVEs in dependencies. It does \*\*not\*\* find code logic flaws.

Conveyor finds both.



Total: 3 critical, 6 important, 1 optional.

