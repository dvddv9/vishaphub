# DVGA core/views.py Ч 8 critical vulnerabilities
**File:** core/views.py (~500 LOC) | **Level:** D3 | **Cost:** ~$0.007
## Found
- CRITICAL: RCE ?3 Ч resolve_system_debug, resolve_system_diagnostics, ImportPaste.mutate
- CRITICAL: SQLi Ч text("title = '%s' or content = '%s'" % (filter, filter))
- CRITICAL: SSRF + MITM Ч curl --insecure with arbitrary URL
- CRITICAL: Authz Ч delete_all_pastes, edit_paste, create_user без guard
- CRITICAL: Authn Ч plaintext password in SQL
- CRITICAL: Identity spoofing Ч caller-supplied token
- CRITICAL: Concurrency Ч SELECT>DELETE without row-lock
- CRITICAL: Scalability Ч global Event Subject breaks with replicas>1
## Resilience: 2/10
## STRIDE: 13 threats, 8 critical
