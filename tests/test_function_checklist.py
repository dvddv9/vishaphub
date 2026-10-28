# -*- coding: utf-8 -*-
"""Checks for plain service functions (no HTTP handlers): found on a blind user_service.py (2026-10-28)."""
from src.tools.route_checklist import checklist
from src.tools.static_scan import scan_material

SERVICE = '''
def update_balance(user_id, amount):
    cursor = db.cursor()
    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    balance = cursor.fetchone()[0]
    cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (balance + amount, user_id))
    db.commit()


def transfer_funds(from_user, to_user, amount):
    cursor.execute("SELECT balance FROM users WHERE id = ?", (from_user,))
    balance = cursor.fetchone()[0]
    if balance >= amount:
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, from_user))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, to_user))


def process_payment(user_id, amount):
    if amount <= 0:
        return 0
    cursor.execute("INSERT INTO payments VALUES (?, ?)", (user_id, amount))
'''


def _by_fn(findings):
    out = {}
    for f in findings:
        out.setdefault(f["title"].split("(")[0], set()).add(f["id"])
    return out


def test_transfer_funds_gets_race_bounds_and_rowcount_findings():
    got = _by_fn(checklist(SERVICE, "python")["findings"])["transfer_funds"]
    assert {"func-check-then-act", "func-amount-no-bounds", "func-unchecked-rowcount"} <= got


def test_update_balance_is_a_lost_update_with_no_bounds():
    got = _by_fn(checklist(SERVICE, "python")["findings"])["update_balance"]
    assert {"func-read-modify-write", "func-amount-no-bounds"} <= got


def test_process_payment_with_a_positive_check_has_no_bounds_finding():
    got = _by_fn(checklist(SERVICE, "python")["findings"]).get("process_payment", set())
    assert "func-amount-no-bounds" not in got


def test_relative_update_is_not_a_lost_update():
    code = ('def add(uid, amount):\\n'
            '    cursor.execute("SELECT balance FROM users WHERE id = ?", (uid,))\\n'
            '    cursor.execute("UPDATE users SET balance = ? WHERE id = ? AND balance >= 0", (1, uid))\\n').replace("\\n", "\n")
    got = _by_fn(checklist(code, "python")["findings"]).get("add", set())
    assert "func-check-then-act" not in got


def test_functions_without_sql_are_ignored():
    assert checklist("def f(amount):\n    return amount * 2\n", "python")["findings"] == []


def test_select_star_on_user_table_is_medium_and_not_double_reported():
    code = 'cursor.execute("SELECT * FROM users WHERE id = ?", (i,))\ncursor.execute("SELECT * FROM logs")\n'
    fs = scan_material(code, "x.py")["findings"]
    by_line = {f["line"]: f for f in fs if f["id"].startswith("sql-star")}
    assert by_line[1]["id"] == "sql-star-credentials" and by_line[1]["severity"] == "medium"
    assert by_line[2]["id"] == "sql-star"


def test_a_file_pasted_three_times_is_not_reported_three_times():
    one = SERVICE + '\ndef export(uid):\n    cursor.execute(f"SELECT * FROM users WHERE id = {uid}")\n'
    single = scan_material(one, "x.py")
    triple = scan_material(one * 3, "x.py")
    assert len(triple["findings"]) == len(single["findings"])
    assert triple.get("repeats_collapsed", 0) > 0
    assert any(f.get("also_at") for f in triple["findings"])


def test_identical_lines_in_two_different_functions_stay_separate():
    code = ('def a(i):\n    cursor.execute(f"DELETE FROM t WHERE id = {i}")\n'
            'def b(i):\n    cursor.execute(f"DELETE FROM t WHERE id = {i}")\n')
    sqli = [f for f in scan_material(code, "x.py")["findings"] if f["id"] == "sqli-fstring"]
    assert len(sqli) == 2
