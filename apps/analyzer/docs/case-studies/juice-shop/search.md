\# Juice Shop search.ts — SQL Injection (CWE-89)



\*\*File:\*\* routes/search.ts (\~70 lines)

\*\*Cost:\*\* \~$0.007

\*\*Time:\*\* \~60 sec



\## Found



\*\*CRITICAL: SQL Injection (CWE-89)\*\*



`models.sequelize.query(\\`SELECT \* FROM Products WHERE ... LIKE '%${criteria}%' ...\\`)`

— user input `req.query.q` interpolated into raw SQL without parameterization.



\### Impact



\- UNION-based exfiltration of `Users.email`, `Users.password`, `sqlite\_master`.

\- Substring-200 is NOT protection — UNION payload fits.

\- Leak is irreversible.



\### Also



\- 11 risk nodes total.

\- Internal contradiction: handler exploits AND detects SQLi.

\- `LIKE '%...%'` without LIMIT → DoS.

\- Challenge detection masks the defect.



\### Fix



1\. Parameterize query.

2\. Rotate passwords.

3\. Audit DB access.

4\. Add rate limiting.

