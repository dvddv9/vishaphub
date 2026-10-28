\# Case Study: Go stdlib



\*\*Source:\*\* go/src/net/http/server.go

\*\*Level:\*\* D3

\*\*Cost:\*\* $0.0074



\---



\## What Vishap found



\### 1. CRITICAL - Request smuggling via CL/TE conflict



Content-Length / Transfer-Encoding conflict.



\*\*Fix:\*\* RFC 7230 3.3.3 validation.



\### 2. CRITICAL - DoS via slow connections



\*\*Fix:\*\* ReadHeaderTimeout, ReadTimeout, WriteTimeout, IdleTimeout.



\### 3. IMPORTANT - HTTP/2 handoff race



\*\*Fix:\*\* Ownership state machine.



\### 4. IMPORTANT - werr only captures first error



\### 5. IMPORTANT - Deprecated API exported



\---



\## Why this matters



CL/TE smuggling — expert-level security finding.



\*\*Vishap found it in 60 seconds.\*\*



Cost: \*\*$0.0074\*\*.



\---



\## Reproduce



&#x20;   vishap analyze data/real\_cases/go\_http\_server.go

