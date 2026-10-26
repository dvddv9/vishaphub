
# -*- coding: utf-8 -*-
"""
Vishap — FastAPI приложение.
"""
from contextlib import asynccontextmanager
import json
import os
import time
import uuid
from datetime import datetime

from fastapi import Header, FastAPI, HTTPException, Depends, BackgroundTasks, Request, Query
from typing import Literal
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.config import APP_NAME, PORT, DATA_DIR, validate_config
from src.version import __version__
from src.observability.logging import (
    setup_logging,
    get_logger,
    bind_request_id,
    clear_context,
)
from src.observability.metrics import get_metrics_output, observe_http_request
from src.observability.tracing import setup_tracing, traced
from src.pipeline.batch import run_batch
from src.storage.history import load_history
from src.api.auth import verify_api_key, is_auth_enabled
from src.api.rate_limit import rate_limit_analyze, rate_limit_read
from src.api.jobs import (
    create_job_async, get_job_async, update_job_async, delete_job_async,
)
from src.api.audit import DEFAULT_LIMIT, MAX_LIMIT, export_audit
from src.api.tasks import run_analysis_task
from src.api.celery_app import broker_available
from src.github_app.webhook import handle_webhook
from src.api.job_store import tenant_scope
from src.auth.middleware import current_tenant, current_user
from src.auth.sso import saml_callback, saml_login
from src.api.gdpr import delete_user_data, export_user_data
from src.api.reports import InvalidReportPath, report_path, save_report
from src.api.webhooks import notify_webhook
from datetime import UTC
from src.tools.sarif import to_sarif
from src.api import llm_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_config()
    print(f"=== {APP_NAME} API запускается ===")
    print(f"Документация: http://localhost:{PORT}/docs")
    yield
    print(f"=== {APP_NAME} API останавливается ===")


setup_logging()
log = get_logger(__name__)
setup_tracing()


# Fail-closed: без CONVEYOR_API_KEY — не стартуем (кроме тестов)
import os as _os
if not _os.getenv("CONVEYOR_API_KEY") and _os.getenv("VISHAP_ALLOW_NO_KEY") != "1":
    raise RuntimeError("CONVEYOR_API_KEY is required (fail-closed). Set it in .env or use VISHAP_ALLOW_NO_KEY=1 for tests.")

# Exact extra origins for a deployed UI, e.g.
#   VISHAP_CORS_ORIGINS=https://vishap.vercel.app,https://app.example.com
_CORS_EXTRA_ORIGINS = [
    o.strip().rstrip("/")
    for o in _os.getenv("VISHAP_CORS_ORIGINS", "").split(",")
    if o.strip() and o.strip() != "*"
]

app = FastAPI(
    title=f"{APP_NAME} API",
    description="Vishap — 6-стадийный LLM-конвейер для анализа материалов",
    version=__version__,
    lifespan=lifespan,
)

import asyncio as _asyncio
_analyze_locks: dict[str, _asyncio.Lock] = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        *_CORS_EXTRA_ORIGINS,
    ],
    # Loopback + the desktop shell only. Shared hosting domains (*.vercel.app,
    # *.onrender.com, *.fly.dev) are NOT wildcarded: anyone can register a
    # subdomain there. List your own deployed UI in VISHAP_CORS_ORIGINS.
    allow_origin_regex=(
        r"^(https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"
        r"|tauri://localhost|https?://tauri\.localhost)$"
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "X-LLM-Api-Key", "X-LLM-Provider", "X-LLM-Model", "Authorization", "X-Requested-With"],
    expose_headers=["X-Request-Id"],
    allow_private_network=True,
)
cors_app = app  # backward-compat alias for `uvicorn.run(cors_app, ...)`


@app.middleware("http")
async def log_requests(request, call_next):
    request_id = str(uuid.uuid4())[:8]
    bind_request_id(request_id)
    start = time.time()
    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 2)
        log.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        observe_http_request(request.method, request.url.path, response.status_code)
        return response
    except Exception as e:
        duration_ms = round((time.time() - start) * 1000, 2)
        log.error(
            "http_request_error",
            method=request.method,
            path=request.url.path,
            error=str(e),
            duration_ms=duration_ms,
            exc_info=True,
        )
        raise
    finally:
        clear_context()


# === Pydantic-схемы ===

class AnalyzeRequest(BaseModel):
    force: bool = False
    material: str = Field(..., max_length=200_000, description="Материал: код, spec, logs и т.п.")
    filename: str = Field(default="input.txt", description="Имя файла")
    verbose: bool = Field(default=False, description="Подробный вывод")


class AnalyzeResponse(BaseModel):
    session_id: str
    filename: str
    version: str = __version__
    level: str | None = None
    route: list | None = None
    final_markdown: str
    timestamp: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    audit_id: str = ""
    material_hash: str = ""
    material_hash_full: str = ""
    truncated: bool = False
    original_size: int = 0
    verdict: str = ""
    pii_detected: bool = False
    compliance_flags: list = []
    audit: dict = {}
    completeness: dict = {}


class HistoryItem(BaseModel):
    session_id: str
    filename: str
    level: str | None = None
    route: list | None = None
    material_size: int
    timestamp: str
    verdict: str | None = None
    pii_detected: bool | None = None


class BatchItem(BaseModel):
    material: str = Field(..., description="Материал / spec / logs")
    filename: str = Field(default="input.txt", description="Имя файла")


class BatchRequest(BaseModel):
    items: list[BatchItem] = Field(..., description="Список материалов")
    max_concurrent: int = Field(default=3, ge=1, le=10, description="Параллелизм")


class BatchResponseItem(BaseModel):
    session_id: str | None = None
    filename: str
    level: str | None = None
    route: list | None = None
    final_markdown: str | None = None
    verdict: str | None = None
    pii_detected: bool | None = None
    error: str | None = None


class BatchResponse(BaseModel):
    results: list[BatchResponseItem]
    count: int
    max_concurrent: int


class CheckoutRequest(BaseModel):
    email: str
    success_url: str
    cancel_url: str


class InvoiceRequest(BaseModel):
    customer_id: str
    description: str
    amount_cents: int


# === Endpoints ===

@app.get("/version")
async def get_version():
    """Return current Vishap version."""
    from src.version import __version__
    return {"version": __version__}


@app.get("/")
async def root():
    return {
        "app": APP_NAME,
        "version": __version__,
        "docs": "/docs",
        "endpoints": [
            "/analyze", "/analyze/async", "/analyze/batch", "/analyze/sarif",
            "/history", "/report/{job_id}", "/report/{job_id}/download",
            "/llm/config", "/health", "/docs",
        ],
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
    }


@app.delete("/status/{job_id}", dependencies=[Depends(verify_api_key), Depends(rate_limit_read)])
async def delete_status(job_id: str, tenant: str = Depends(current_tenant)):
    with tenant_scope(tenant):
        deleted = await delete_job_async(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="job not found")
    return {"deleted": True, "job_id": job_id}


@app.get("/metrics")
async def metrics():
    return Response(
        content=get_metrics_output(),
        media_type="text/plain; version=0.0.4",
    )


@app.post("/webhook/github")
async def github_webhook(request: Request):
    _secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    _sig = request.headers.get("X-Hub-Signature-256", "")
    if not _secret or not _sig or not verify_webhook_signature(await request.body(), _sig, _secret):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="invalid GitHub signature")
    return await handle_webhook(request)



@app.post("/webhook/lemonsqueezy")
async def lemonsqueezy_webhook(request: Request):
    """Lemon Squeezy webhook: HMAC verify, idempotency, tenant status update."""
    from src.api.tenants import get_store
    from src.billing.lemonsqueezy.webhook import handle_lemonsqueezy_webhook

    store = get_store()
    payload = await request.body()
    sig = request.headers.get("X-Signature", "")
    async with store._session_factory() as session:
        return await handle_lemonsqueezy_webhook(payload, sig, session)
@app.post("/billing/checkout")
async def checkout(req: CheckoutRequest):
    return create_checkout_session(req.email, req.success_url, req.cancel_url)


@app.post("/billing/invoice", dependencies=[Depends(current_user)])
async def create_invoice_endpoint(req: InvoiceRequest):
    if req.amount_cents <= 0:
        raise HTTPException(status_code=400, detail="amount_cents must be positive")
    return create_invoice(req.customer_id, req.description, req.amount_cents)


@app.get("/billing/products")
async def billing_products():
    return list_prices()


@app.get("/api/me/data")
async def export_my_data(user: dict = Depends(current_user)):
    with tenant_scope(user["tenant_id"]):
        return await export_user_data(user["tenant_id"])


@app.delete("/api/me")
async def delete_my_account(user: dict = Depends(current_user)):
    with tenant_scope(user["tenant_id"]):
        return await delete_user_data(user["tenant_id"])


@app.get("/auth/sso/login")
async def sso_login(tenant: str = Query(..., description="Tenant/org id requesting SSO")):
    return await saml_login(tenant)


@app.post("/auth/sso/callback")
async def sso_callback(payload: dict):
    # SEC-6: validate SAML assertion (CWE-347)
    from src.auth.saml_guard import validate_saml_assertion
    if not validate_saml_assertion(payload):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="invalid SAML assertion")
    return await saml_callback(payload)



def verify_webhook_signature(payload: bytes, signature: str, secret: str, algo: str = "sha256") -> bool:
    """Verify webhook signature (GitHub). Returns True if valid."""
    import hmac, hashlib
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), payload, getattr(hashlib, algo)).hexdigest()
    return hmac.compare_digest(expected, signature.replace("sha256=", "").replace("sha1=", ""))


def _need_user_llm_key(x_llm_api_key: str | None) -> None:
    """401 when the operator runs in user-key-only mode and no key was sent."""
    from src.llm.client import require_user_key
    if require_user_key() and not (x_llm_api_key or "").strip():
        raise HTTPException(
            status_code=401,
            detail="This server does not use its own LLM key. Send yours in the X-LLM-Api-Key header.",
        )


def _apply_llm_request(key: str | None, provider: str | None, model: str | None):
    """Validate the caller's LLM choice and bind it to this request's context.

    Returns (key, target). ``target`` is (base_url, model) from the server-side
    provider allow-list or None (use the server's configured endpoint).
    """
    from src.llm import providers
    from src.llm.client import set_api_key, set_llm_target
    _need_user_llm_key(key)
    key = (key or "").strip() or None
    try:
        target = providers.resolve(provider, model)
    except providers.ProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if target and not key:
        raise HTTPException(
            status_code=400,
            detail="Choosing an LLM provider requires your own key (X-LLM-Api-Key).",
        )
    set_api_key(key)
    set_llm_target(target)
    return key, target


@app.get("/providers", dependencies=[Depends(verify_api_key)])
async def llm_providers():
    """LLM providers a caller may pick (bring-your-own-key)."""
    from src.llm import providers
    return {"providers": providers.list_providers()}


@app.post("/analyze", response_model=AnalyzeResponse, dependencies=[Depends(verify_api_key), Depends(rate_limit_analyze)])
@traced("analyze")
async def analyze(req: AnalyzeRequest,
                  x_llm_api_key: str | None = Header(None, alias="X-LLM-Api-Key"),
                  x_llm_provider: str | None = Header(None, alias="X-LLM-Provider"),
                  x_llm_model: str | None = Header(None, alias="X-LLM-Model")):
    if not req.material.strip():
        raise HTTPException(status_code=400, detail="material must not be empty")

    _apply_llm_request(x_llm_api_key, x_llm_provider, x_llm_model)
    from src.pipeline.orchestrator import compute_hash
    from src.storage.history import find_done_by_hash

    material_hash = compute_hash(req.material)
    existing = None if getattr(req, 'force', False) else find_done_by_hash(material_hash)

    if existing:
        cached_session = existing.get("session_id", "")
        result_file = DATA_DIR / f"result_{cached_session}.json"
        if result_file.exists():
            cached = json.loads(result_file.read_text(encoding="utf-8"))
            stage0c = cached.get("stage0") or {}
            stage1c = cached.get("stage1") or {}
            stage2c = cached.get("stage2") or {}
            tokens_in_c = sum((s or {}).get("_meta", {}).get("tokens_in", 0) for s in [stage0c, stage1c, stage2c])
            tokens_out_c = sum((s or {}).get("_meta", {}).get("tokens_out", 0) for s in [stage0c, stage1c, stage2c])
            return AnalyzeResponse(
                session_id=cached.get("session_id", cached_session),
                filename=cached.get("filename", req.filename),
                version=cached.get("version", __version__),
                level=stage0c.get("level"),
                route=stage0c.get("route"),
                final_markdown=cached.get("final_markdown", ""),
                timestamp=cached.get("timestamp", ""),
                tokens_in=tokens_in_c,
                tokens_out=tokens_out_c,
                cost_usd=cached.get("cost_usd", 0.0),
                audit=cached.get("audit", {}),
                completeness=cached.get("completeness", {}),
                material_hash_full=cached.get("audit", {}).get("material_hash_full", cached.get("material_hash", "")),
                truncated=cached.get("audit", {}).get("truncated", False),
                original_size=cached.get("audit", {}).get("original_size", 0),
                cached=True,
                audit_id=cached.get("audit", {}).get("audit_id", ""),
                material_hash=cached.get("audit", {}).get("material_hash", ""),
                verdict=cached.get("audit", {}).get("critique_verdict", ""),
                pii_detected=bool(cached.get("audit", {}).get("pii_detected", False)),
                compliance_flags=cached.get("audit", {}).get("compliance_flags", []),
            )

    try:
        from src.pipeline.orchestrator import run_pipeline_async
        result = await run_pipeline_async(
            material=req.material,
            filename=req.filename,
            verbose=False,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")

    stage0 = result.get("stage0") or {}
    stage1 = result.get("stage1") or {}
    stage2 = result.get("stage2") or {}

    tokens_in = sum(
        (s or {}).get("_meta", {}).get("tokens_in", 0)
        for s in [stage0, stage1, stage2]
    )
    tokens_out = sum(
        (s or {}).get("_meta", {}).get("tokens_out", 0)
        for s in [stage0, stage1, stage2]
    )
    from src.pipeline.cost import sum_stage_costs
    stage3 = result.get("stage3") or {}
    stage4 = result.get("stage4") or {}
    cost_usd = sum_stage_costs([stage0, stage1, stage2, stage3, stage4])

    _audit = result.get("audit", {}) or {}
    return AnalyzeResponse(
        session_id=result["session_id"],
        filename=result.get("filename", req.filename),
        version=__version__,
        level=stage0.get("level"),
        route=stage0.get("route"),
        final_markdown=result["final_markdown"],
        timestamp=result.get("timestamp", datetime.now(UTC).isoformat()),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        audit_id=_audit.get("audit_id", ""),
        material_hash=_audit.get("material_hash", ""),
        verdict=_audit.get("critique_verdict", ""),
        material_hash_full=_audit.get("material_hash_full", ""),
        truncated=_audit.get("truncated", False),
        original_size=_audit.get("original_size", 0),
        pii_detected=bool(_audit.get("pii_detected", False)),
        compliance_flags=_audit.get("compliance_flags", []),
        audit=result.get("audit", {}),
        completeness=result.get("completeness", {}),
    )


@app.post("/analyze/secure", dependencies=[Depends(current_user)])
async def analyze_secure(req: AnalyzeRequest, user: dict = Depends(current_user)):
    with tenant_scope(user["tenant_id"]):
        return await analyze(req, x_llm_api_key=None, x_llm_provider=None, x_llm_model=None)


@app.post("/analyze/batch", response_model=BatchResponse, dependencies=[Depends(verify_api_key), Depends(rate_limit_analyze)])
async def analyze_batch(req: BatchRequest,
                        x_llm_api_key: str | None = Header(None, alias="X-LLM-Api-Key"),
                        x_llm_provider: str | None = Header(None, alias="X-LLM-Provider"),
                        x_llm_model: str | None = Header(None, alias="X-LLM-Model")):
    if not req.items:
        raise HTTPException(status_code=400, detail="items must not be empty")
    for i, item in enumerate(req.items):
        if not item.material.strip():
            raise HTTPException(
                status_code=400,
                detail=f"items[{i}].material must not be empty",
            )

    _apply_llm_request(x_llm_api_key, x_llm_provider, x_llm_model)

    materials = [(item.material, item.filename) for item in req.items]

    try:
        results = run_batch(
            materials,
            max_concurrent=req.max_concurrent,
            verbose=False,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch error: {str(e)}")

    response_items = []
    for r, item in zip(results, req.items):
        if r is None or "error" in r:
            response_items.append(BatchResponseItem(
                filename=item.filename,
                error=(r or {}).get("error", "unknown"),
            ))
            continue

        stage0 = r.get("stage0", {}) or {}
        audit = r.get("audit", {}) or {}

        response_items.append(BatchResponseItem(
            session_id=r.get("session_id"),
            filename=item.filename,
            level=stage0.get("level"),
            route=stage0.get("route"),
            final_markdown=r.get("final_markdown"),
            verdict=audit.get("critique_verdict"),
            pii_detected=audit.get("pii_detected"),
        ))

    return BatchResponse(
        results=response_items,
        count=len(response_items),
        max_concurrent=req.max_concurrent,
    )


@app.post("/analyze/sarif", dependencies=[Depends(verify_api_key), Depends(rate_limit_analyze)])
async def analyze_sarif(req: AnalyzeRequest):
    result = await analyze(req)

    audit = result.audit.model_dump() if hasattr(result, "audit") else {}

    sast_result = None
    sca_result = None
    if isinstance(audit, dict):
        sast_tools = audit.get("sast_tools", {})
        if sast_tools:
            sast_result = {
                "total_findings": audit.get("sast_findings", 0),
                "high_priority": audit.get("sast_high_priority", 0),
                "bandit": {"available": True, "summary": sast_tools.get("bandit", {}), "findings": []},
                "semgrep": {"available": True, "summary": sast_tools.get("semgrep", {}), "findings": []},
            }

    sarif = to_sarif(
        audit=audit if isinstance(audit, dict) else {},
        sast_result=sast_result,
        sca_result=sca_result,
        source_file=req.filename,
    )
    return JSONResponse(content=sarif)


@app.get("/history", response_model=list[HistoryItem])
async def history(limit: int = 20, tenant: str = Depends(current_tenant)):
    with tenant_scope(tenant):
        items = load_history(tenant_id=tenant)
        return [
            HistoryItem(
                session_id=item.get("session_id", ""),
                filename=item.get("filename", ""),
                level=item.get("level"),
                route=item.get("route"),
                material_size=item.get("material_size", 0),
                timestamp=item.get("timestamp", ""),
                verdict=item.get("verdict"),
                pii_detected=item.get("pii_detected"),
            )
            for item in items[-limit:]
        ]


@app.post("/history/clear", dependencies=[Depends(verify_api_key), Depends(rate_limit_read)])
async def history_clear(tenant: str = Depends(current_tenant)):
    from src.storage.history import clear_history

    with tenant_scope(tenant):
        removed = clear_history(tenant_id=tenant)
    return {"status": "ok", "removed": removed}


@app.get("/audit/export", dependencies=[Depends(verify_api_key), Depends(rate_limit_read)])
async def audit_export(
    format: Literal["csv", "json"] = "csv",
    from_date: str | None = Query(None, alias="from", description="ISO 8601 lower bound"),
    to_date: str | None = Query(None, alias="to", description="ISO 8601 upper bound"),
    status: Literal["queued", "running", "done", "failed"] | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    tenant: str = Depends(current_tenant),
):
    with tenant_scope(tenant):
        return await export_audit(
            format=format,
            from_date=from_date,
            to_date=to_date,
            status=status,
            limit=limit,
        )


async def _run_job_async(job_id: str, req: "AnalyzeRequest", tenant: str, llm_key: str | None = None,
                         llm_target: tuple[str, str] | None = None):
    from src.llm.client import set_api_key, set_llm_target
    from src.pipeline.orchestrator import run_pipeline_async
    set_api_key(llm_key)  # per-job; never persisted or logged
    set_llm_target(llm_target)
    with tenant_scope(tenant):
        await update_job_async(
            job_id, status="running", started_at=datetime.now(UTC).isoformat()
        )
        try:
            result = await run_pipeline_async(
                material=req.material,
                filename=req.filename or "unknown",
                verbose=False,
            )
            await update_job_async(
                job_id,
                status="done",
                result=result,
                finished_at=datetime.now(UTC).isoformat(),
            )
            save_report(job_id, (result or {}).get("final_markdown"))
            await notify_webhook(
                "job.completed", {"job_id": job_id, "tenant_id": tenant, "status": "done"}
            )
        except Exception as e:
            await update_job_async(
                job_id,
                status="failed",
                error=str(e),
                finished_at=datetime.now(UTC).isoformat(),
            )
            await notify_webhook(
                "job.failed",
                {"job_id": job_id, "tenant_id": tenant, "status": "failed", "error": str(e)},
            )


@app.post("/analyze/async", dependencies=[Depends(verify_api_key), Depends(rate_limit_analyze)])
@traced("analyze_async")
async def analyze_async(req: "AnalyzeRequest", background: BackgroundTasks,
                        tenant: str = Depends(current_tenant),
                        x_llm_api_key: str | None = Header(None, alias="X-LLM-Api-Key"),
                        x_llm_provider: str | None = Header(None, alias="X-LLM-Provider"),
                        x_llm_model: str | None = Header(None, alias="X-LLM-Model")):
    llm_key, llm_target = _apply_llm_request(x_llm_api_key, x_llm_provider, x_llm_model)
    with tenant_scope(tenant):
        job_id = await create_job_async(
            filename=req.filename or "unknown", tenant_id=tenant
        )
        await notify_webhook(
            "job.queued",
            {
                "job_id": job_id,
                "tenant_id": tenant,
                "filename": req.filename or "unknown",
                "status": "queued",
            },
        )
        if llm_key is None and broker_available():
            run_analysis_task.delay(job_id, req.material, req.filename or "unknown", tenant)
        else:
            # A caller-supplied key stays in this process: it is never put on the
            # Celery broker / result backend.
            if llm_key is None:
                log.warning("celery_broker_unavailable", job_id=job_id)
            background.add_task(_run_job_async, job_id, req, tenant, llm_key, llm_target)
        return {"job_id": job_id, "status": "queued"}


@app.get("/status/{job_id}")
async def get_status(job_id: str, tenant: str = Depends(current_tenant)):
    with tenant_scope(tenant):
        job = await get_job_async(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "filename": job["filename"],
            "created_at": job["created_at"],
            "started_at": job["started_at"],
            "finished_at": job["finished_at"],
            "error": job["error"],
        }


@app.get("/report/{job_id}")
async def get_report(job_id: str, tenant: str = Depends(current_tenant)):
    with tenant_scope(tenant):
        job = await get_job_async(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        if job["status"] != "done":
            raise HTTPException(
                status_code=409,
                detail=f"job not done: {job['status']}",
            )
        return job["result"]


@app.get("/report/{job_id}/download")
async def download_report(job_id: str, tenant: str = Depends(current_tenant)):
    with tenant_scope(tenant):
        job = await get_job_async(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")

        try:
            path = report_path(job_id)
        except InvalidReportPath:
            path = None

        if path is not None and path.exists():
            return FileResponse(
                path,
                media_type="text/markdown",
                filename=f"{job_id}.md",
            )

        markdown = (job.get("result") or {}).get("final_markdown")
        if markdown:
            if path is not None:
                save_report(job_id, markdown)
            return Response(
                content=markdown,
                media_type="text/markdown",
                headers={"Content-Disposition": f'attachment; filename="{job_id}.md"'},
            )

        raise HTTPException(status_code=404, detail="report not found")


# === Регистрация LLM-конфигурации (перенесено сюда, чтобы точно работало) ===
app.include_router(llm_config.router)


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("VISHAP_HOST", "127.0.0.1")  # default loopback for desktop; override with VISHAP_HOST=0.0.0.0 for Docker
    print(f"[Auth] API key {'set' if is_auth_enabled() else 'NOT set'} -- binding to {host}")
    uvicorn.run(
        cors_app,
        host=host,
        port=PORT,
        reload=False,
    )