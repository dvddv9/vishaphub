# -*- coding: utf-8 -*-
"""Regressions found by running Vishap on a blind user_service.py (2026-10-28)."""
from src.tools.dataflow import analyze_dataflow
from src.tools.redact import redact_pii
from src.tools.static_scan import scan_material

SQL_F = '''
def reset(new_password):
    cursor.execute(f"UPDATE users SET password = '{new_password}' WHERE id = 1")
'''


def _rules(code, name="x.py"):
    return [(f["id"], f["line"]) for f in scan_material(code, name)["findings"]]


def test_fstring_password_interpolation_is_not_a_hardcoded_secret():
    assert not [r for r in _rules(SQL_F) if r[0].startswith("secret-hardcoded")]
    assert any(r[0] == "sqli-fstring" for r in _rules(SQL_F))


def test_placeholders_and_templates_are_not_secrets():
    code = ('cur.execute("UPDATE u SET password = %s WHERE id = 1", (p,))\n'
            'q = "password = :pwd_value"\n'
            'token = "${TOKEN_FROM_ENV_VALUE}"\n')
    assert not [r for r in _rules(code) if r[0].startswith("secret-hardcoded")]


def test_real_hardcoded_secrets_are_still_flagged():
    code = 'PASSWORD = "hunter2hunter2"\nAPI_KEY = "abcdef1234567890"\n'
    hits = [r for r in _rules(code) if r[0].startswith("secret-hardcoded")]
    assert {line for _, line in hits} == {1, 2}


def test_redaction_leaves_interpolated_sql_untouched():
    out, mapping = redact_pii(SQL_F)
    assert out == SQL_F
    assert "hardcoded_password" not in mapping


def test_redaction_keeps_the_variable_name():
    # built at run time so this file does not contain a Stripe-shaped key (GitHub push protection)
    fake_key = "sk_" + "live_" + "A1b2C3d4E5f6G7h8I9j0K1l2"
    out, _ = redact_pii(f'API_KEY = "{fake_key}"\nPASSWORD = "hunter2hunter2"\n')
    assert out.startswith('API_KEY = "<')
    assert 'PASSWORD = "<PASSWORD_REDACTED>"' in out
    assert "hunter2" not in out and "A1b2C3" not in out
    assert redact_pii(out)[0] == out          # idempotent


def test_taint_origin_is_the_argument_not_a_module_level_environ_read():
    code = (
        'import os\nDB_PATH = os.environ.get("DB_PATH", "app.db")\n\n'
        'def create_user(username, email):\n'
        '    query = f"INSERT INTO users VALUES (\'{username}\', \'{email}\')"\n'
        '    cursor.execute(query)\n'
    )
    flow = analyze_dataflow(code)
    assert flow["source"]["name"] in ("username", "email")
    assert flow["source"]["content"].startswith("arg:")
    assert flow["sink"]["line"] == 6


def test_taint_origin_follows_a_source_call_assigned_in_the_function():
    code = (
        'import os\nDB_PATH = os.environ.get("DB_PATH")\n\n'
        'def view():\n'
        '    uid = request.args.get("id")\n'
        '    sql = "SELECT * FROM t WHERE id=" + uid\n'
        '    cursor.execute(sql)\n'
    )
    flow = analyze_dataflow(code)
    assert flow["source"]["name"].startswith("request.args")
