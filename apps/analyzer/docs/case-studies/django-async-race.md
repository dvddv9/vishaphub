\# Case Study: Django



\*\*Source:\*\* django/db/models/query.py

\*\*Level:\*\* D3

\*\*Cost:\*\* $0.0068



\---



\## What Vishap found



\### 1. CRITICAL - Shared mutable obj.\_state.peers



Shared mutable list, append without lock.



\*\*Fix:\*\* Protect with lock.



\### 2. IMPORTANT - sync\_to\_async per-chunk



Called per chunk.



\*\*Fix:\*\* Batch chunks.



\### 3. IMPORTANT - Positional column binding without validation



\*\*Fix:\*\* Validate column count.



\### 4. IMPORTANT - from\_db() removed in Django 2028



\*\*Fix:\*\* Migrate to fetch\_mode.



\### 5. IMPORTANT - RemovedInDjango2029Warning not used



\*\*Fix:\*\* Remove or use.



\---



\## Why this matters



Race in peers + sync\_to\_async per-chunk — real Django ORM issues.



\*\*Vishap found them in 60 seconds.\*\*



Cost: \*\*$0.0068\*\*.



\---



\## Reproduce



&#x20;   vishap analyze data/real\_cases/django\_query.py

