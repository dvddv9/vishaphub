# -*- coding: utf-8 -*-
"""Logic pass, language sniffing by content, route-chain label, baseline compliance."""
from src.tools.compliance import BASELINE_STANDARDS, enrich_compliance
from src.tools.patterns import detect_exploitability
from src.tools.static_scan import detect_language, render_markdown, scan_material

FLASK = (
    "import os, sqlite3\n"
    "from flask import Flask, request, jsonify\n"
    "\n"
    "app = Flask(__name__)\n"
    "_cache = {}\n"
    "\n"
    "@app.get(\"/items\")\n"
    "def items(page=0, size=20, seen=[]):\n"
    "    size = int(request.args.get(\"size\", size))\n"
    "    rows = sqlite3.connect(\"x.db\").execute(\"SELECT id FROM items\").fetchall()\n"
    "    return jsonify(rows[page * size : page * size + size + 1])\n"
)


def _ids(result):
    return {f["id"] for f in result["findings"]}


# --- language by content ------------------------------------------------------

def test_pasted_python_with_dict_literal_is_python_not_unknown():
    assert detect_language("pasted.txt", FLASK) == "python"


def test_language_sniff_keeps_old_behaviour():
    assert detect_language("noext", "import os\n") == "python"
    assert detect_language("noext", "plain words") == "unknown"
    assert detect_language("x.py", "") == "python"


def test_javascript_is_still_detected_by_content():
    js = "const express = require('express');\nconst app = express();\napp.get('/', (req, res) => res.send('ok'));\n"
    assert detect_language("pasted.txt", js) == "javascript"


# --- logic rules --------------------------------------------------------------

def test_logic_rules_find_the_pagination_bugs():
    r = scan_material(FLASK, "pasted.txt")
    assert {"logic-mutable-default", "logic-unbounded-limit", "logic-slice-plus-one"} <= _ids(r)
    assert r["logic_findings"] == 3
    assert all(f["kind"] == "logic" for f in r["findings"] if f["id"].startswith("logic-"))


def test_logic_finding_without_cwe_does_not_pollute_cwe_list():
    r = scan_material("def f(a, seen=[]):\n    return seen\n", "x.py")
    assert "logic-mutable-default" in _ids(r)
    assert "" not in r["cwe_ids"]
    assert "logic" in render_markdown(r, "x.py")


def test_logic_rules_stay_quiet_on_correct_code():
    ok = (
        "def f(a, seen=None, tail=()):\n"
        "    size = min(int(request.args.get('size', 20)), 100)\n"
        "    chunk = rows[page * size : page * size + size]\n"
        "    if hmac.compare_digest(token, expected):\n"
        "        pass\n"
        "    if password == '' or len(token) == 5 or hash_len == 32 or token == None:\n"
        "        pass\n"
    )
    r = scan_material(ok, "ok.py")
    assert r["logic_findings"] == 0, r["findings"]


def test_timing_unsafe_compare_of_secrets():
    assert "logic-timing-compare" in _ids(scan_material("if row and row[0] == pw:\n    pass\n", "a.py"))
    assert "logic-timing-compare" in _ids(scan_material("if token == expected:\n    pass\n", "a.py"))
    assert "logic-timing-compare" in _ids(scan_material("if (token === saved) {}\n", "a.js"))


def test_off_by_one_loops():
    assert "logic-range-len-plus-one" in _ids(scan_material("for i in range(len(xs) + 1):\n    pass\n", "a.py"))
    assert "logic-js-lte-length" in _ids(scan_material("for (let i = 0; i <= arr.length; i++) {}\n", "a.js"))
    assert "logic-js-lte-length" not in _ids(scan_material("for (let i = 0; i < arr.length; i++) {}\n", "a.js"))


# --- exploitability: no JS chain for Python -----------------------------------

def test_flask_decorator_is_not_reported_as_js_route():
    r = detect_exploitability(FLASK)
    path = r["exploit_path"][0]["path"]
    assert path.startswith("py_route"), path
    assert "js_route" not in path


def test_chain_names_the_real_sink_and_not_a_fixed_guess():
    assert detect_exploitability(FLASK)["exploit_path"][0]["path"] == "py_route -> sql"
    plain = "from flask import Flask\napp = Flask(__name__)\n\n@app.get('/')\ndef index():\n    return 'ok'\n"
    r = detect_exploitability(plain)
    assert r["exploit_path"][0]["path"] == "py_route -> handler"
    assert r["blast_indicators"] == []


def test_express_still_gets_js_route():
    js = "const express = require('express');\nconst app = express();\napp.get('/x', (req, res) => { require('child_process').execSync(req.query.c); });\n"
    r = detect_exploitability(js)
    assert r["exploit_path"][0]["path"] == "js_route -> exec"
    assert "RCE" in r["blast_indicators"]


# --- compliance: sector standards only when triggered --------------------------

def test_sector_standards_are_not_added_without_a_trigger():
    r = enrich_compliance(["CWE-89", "CWE-200", "CWE-22"], [])
    assert set(r["compliance_standards"]) <= set(BASELINE_STANDARDS)
    assert "HIPAA" not in r["compliance_controls"]
    assert "PCI-DSS" not in r["compliance_controls"]


def test_flagged_standard_is_reported():
    r = enrich_compliance(["CWE-89", "CWE-200"], ["HIPAA"])
    assert "HIPAA" in r["compliance_controls"]
    assert "SOC2" in r["compliance_controls"]


def test_explicit_standards_filter_still_wins():
    r = enrich_compliance(["CWE-89"], [], standards=["PCI-DSS"])
    assert list(r["compliance_controls"]) == ["PCI-DSS"]
