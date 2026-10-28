# -*- coding: utf-8 -*-
"""Run Vishap tests.

Usage:
    python run_tests.py          # unit + mock (fast, no LLM)
    python run_tests.py --all    # all tests (includes real LLM)
"""
import subprocess
import sys


def run(path):
    print(f"\n=== {path} ===")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", path],
        cwd="C:/AI/conveyor_app",
    )
    if result.returncode == 0:
        PASSED += 1
    else:
        FAILED += 1
    if result.returncode == 0:
        PASSED += 1
    else:
        FAILED += 1
    return result.returncode


def main():
    rc = 0
    rc |= run("tests/test_conftest_data_dir.py")
    rc |= run("tests/test_version_sync.py")
    rc |= run("tests/test_tools.py")
    rc |= run("tests/test_patterns.py")
    rc |= run("tests/test_patterns_java.py")
    rc |= run("tests/test_patterns_c.py")
    rc |= run("tests/test_pipeline_mock.py")
    rc |= run("tests/test_baseline.py")
    rc |= run("tests/test_diff.py")
    rc |= run("tests/test_sbom.py")
    rc |= run("tests/test_sarif.py")
    rc |= run("tests/test_quality_gate.py")
    rc |= run("tests/test_deps.py")
    rc |= run("tests/test_reachability.py")
    rc |= run("tests/test_dataflow.py")
    rc |= run("tests/test_compliance.py")
    rc |= run("tests/test_runbook.py")
    rc |= run("tests/test_security_md.py")
    rc |= run("tests/test_llm_providers.py")
    # rc |= run("tests/test_harness_launcher.py")  # v7.4.0: file removed
    # rc |= run("tests/test_harness_api.py")  # v7.4.1: file removed
    rc |= run("tests/test_job_delete_api.py")
    rc |= run("tests/test_llm_error_failclosed.py")
    rc |= run("tests/test_anomaly.py")
    rc |= run("tests/test_async_imports.py")
    rc |= run("tests/test_async_api.py")
    rc |= run("tests/test_job_store.py")
    rc |= run("tests/test_jobs_shim_iso.py")
    rc |= run("tests/test_job_store_postgres.py")
    rc |= run("tests/test_logging.py")
    rc |= run("tests/test_metrics.py")
    rc |= run("tests/test_fernet.py")
    rc |= run("tests/test_token_metrics.py")
    rc |= run("tests/test_observe.py")
    # rc |= run("tests/test_ui_headers.py")  # v7.4.1: file removed
    # rc |= run("tests/test_ui_async.py")  # v7.4.1: file removed
    # rc |= run("tests/test_ui_badge_version.py")  # v7.4.1: file removed
    # rc |= run("tests/test_api_client.py")  # v7.4.1: file removed
    rc |= run("tests/test_risk_verdict.py")
    rc |= run("tests/test_risk_verdict_security.py")
    rc |= run("tests/test_verdict.py")
    rc |= run("tests/test_verdict_threat_model.py")
    rc |= run("tests/test_verdict_sec_fallback.py")
    rc |= run("tests/test_anomaly_density.py")
    rc |= run("tests/test_pii_copyright.py")
    rc |= run("tests/test_anomaly_code.py")
    rc |= run("tests/test_analyze_concurrency.py")
    rc |= run("tests/test_analyze_contracts.py")
    rc |= run("tests/test_celery_app.py")
    rc |= run("tests/test_tasks.py")
    rc |= run("tests/test_github_auth.py")
    rc |= run("tests/test_github_client.py")
    rc |= run("tests/test_github_webhook.py")
    rc |= run("tests/test_auth_clerk.py")
    rc |= run("tests/test_auth_middleware.py")
    rc |= run("tests/test_stripe_client.py")
    rc |= run("tests/test_billing_webhook.py")
    rc |= run("tests/test_tracing.py")
    rc |= run("tests/test_rls.py")
    rc |= run("tests/test_history.py")
    rc |= run("tests/test_audit_export.py")
    rc |= run("tests/test_billing_invoice.py")
    rc |= run("tests/test_gdpr.py")
    rc |= run("tests/test_webhook.py")
    rc |= run("tests/test_sso.py")
    rc |= run("tests/test_stripe_setup.py")
    rc |= run("tests/test_config_validation.py")
    rc |= run("tests/test_webhook_tenant.py")
    rc |= run("tests/test_clerk_optional.py")
    rc |= run("tests/test_generate_key.py")
    rc |= run("tests/test_verify_api_key.py")
    rc |= run("tests/test_report_download.py")
    rc |= run("tests/test_api_key_hash.py")
    rc |= run("tests/test_email_smtp.py")
    rc |= run("tests/test_clerk_jwt.py")
    rc |= run("tests/test_normalize_path.py")

    if "--all" in sys.argv:
        print("\n[--all] E2E tests (real LLM, slow, uses API):")
        rc |= run("tests/test_e2e.py")
    rc |= run("tests/test_cors_pna.py")
    rc |= run("tests/test_desktop_mode.py")
    rc |= run("tests/test_desktop_startup.py")
    rc |= run("tests/test_docker_distribution.py")
    rc |= run("tests/test_stage2_5_redteam.py")
    rc |= run("tests/test_tauri_desktop.py")
    rc |= run("tests/test_tenants.py")
    rc |= run("tests/test_job_store_postgres_integration.py")

    print(f"\n=== SUMMARY: PASSED={PASSED} FAILED={FAILED} (rc={rc}) ===")
    print(f"\n=== SUMMARY: PASSED={PASSED} FAILED={FAILED} (rc={rc}) ===")
    sys.exit(rc)


if __name__ == "__main__":
    main()