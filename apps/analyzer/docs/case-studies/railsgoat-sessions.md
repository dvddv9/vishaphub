# RailsGoat sessions_controller.rb — 3 critical
**File:** app/controllers/sessions_controller.rb (~35 LOC) | **Level:** D2 | **Cost:** ~$0.007
## Found
- CRITICAL: NameError on failed password — flash[:error] = e.message out of rescue scope
- CRITICAL: Session fixation — no reset_session in create
- CRITICAL: Open redirect — redirect_to path with unvalidated params[:url]
- IMPORTANT: rescue RuntimeError masks internal errors
- IMPORTANT: Two auth paths (session vs cookies) without single source
- IMPORTANT: No rate limiting / lockout / audit
