\# Case Study: Flask



\*\*Source:\*\* flask/app.py

\*\*Level:\*\* D4

\*\*Cost:\*\* $0.0065



\---



\## What Vishap found



\### 1. CRITICAL - SECRET\_KEY=None in production



Session forgery possible.



\*\*Fix:\*\* Require SECRET\_KEY at startup.



\### 2. CRITICAL - Method signature migration (ctx)



Public contract for all subclasses.



\### 3. IMPORTANT - Shim doesn't cover keyword-ctx and \*args



\### 4. IMPORTANT - SESSION\_COOKIE\_SECURE=False



Cookie interception.



\### 5. IMPORTANT - TRUSTED\_HOSTS=None



Host header injection.



\### 6. IMPORTANT - MAX\_CONTENT\_LENGTH=None



DoS via large payloads.



\---



\## Why this matters



4 OWASP Top 10 issues found automatically.



\*\*Vishap found them in 60 seconds.\*\*



Cost: \*\*$0.0065\*\*.



\---



\## Reproduce



&#x20;   vishap analyze data/real\_cases/flask\_app.py

