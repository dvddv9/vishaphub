\# Case Study: Express



\*\*Source:\*\* express/lib/router/index.js

\*\*Level:\*\* D3

\*\*Cost:\*\* $0.0069



\---



\## What Vishap found



\### 1. IMPORTANT - Prototype pollution via mergeParams



mergeParams=true + \_\_proto\_\_ in URL leads to pollution.



\*\*Fix:\*\* Filter \_\_proto\_\_, constructor, prototype.



\*\*Reference:\*\* CVE-2022-24999



\### 2. IMPORTANT - Downstream trusts mutated req.url



\*\*Fix:\*\* Use req.path or req.originalUrl.



\### 3. IMPORTANT - Mutation of self.stack during handle()



\*\*Fix:\*\* Freeze stack after start.



\### 4. IMPORTANT - sync flag not reset



\### 5. IMPORTANT - String sentinel errors not typed



\### 6. OPTIONAL - O(n) dispatch



\---



\## Why this matters



Prototype pollution (CVE-2022-24999) is top-10 Node.js vulnerability.



\*\*Vishap found it in 60 seconds.\*\*



Cost: \*\*$0.0069\*\*.



\---



\## Reproduce



&#x20;   vishap analyze data/real\_cases/express\_router.js

