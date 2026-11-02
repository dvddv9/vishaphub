# -*- coding: utf-8 -*-
"""Findings from the live run of 2026-11-01: rules and recognition the hub missed on pasted text."""
from src.tools.static_scan import detect_language, scan_material


def ids(text, name="pasted.txt"):
    return {f["id"]: f["severity"] for f in scan_material(text, name)["findings"]}


DOCKERFILE = (
    "FROM ubuntu:latest\n"
    "ENV AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
    "ADD https://example.com/install.sh /tmp/install.sh\n"
    "RUN curl -fsSL https://example.com/install.sh | sh\n"
    "RUN chmod 777 /app\n"
    "COPY . /app\n"
    "CMD [\"/app/run.sh\"]\n"
)


def test_a_dockerfile_is_recognised_from_its_text_alone():
    assert detect_language("pasted.txt", DOCKERFILE) == "dockerfile"
    assert detect_language("pasted.txt", "# build\nARG V=1\nFROM alpine:3.20\nRUN true\n") == "dockerfile"


def test_sql_or_prose_with_a_from_line_is_not_a_dockerfile():
    assert detect_language("pasted.txt", "SELECT a\nFROM users\nWHERE x = 1\n") != "dockerfile"
    assert detect_language("pasted.txt", "From the start, we ran the tests.\n") != "dockerfile"


def test_the_dockerfile_rules_find_what_a_reader_would():
    found = ids(DOCKERFILE)
    for rule in ("docker-secret-env", "docker-curl-pipe", "docker-add-url", "docker-chmod-777", "docker-root"):
        assert rule in found, (rule, found)
    assert found["docker-secret-env"] == "high" and found["docker-add-url"] == "medium"


def test_a_clean_dockerfile_is_left_alone():
    clean = 'FROM python:3.12-slim\nENV APP_MODE=prod\nRUN useradd -m app\nUSER app\nCMD ["python", "x.py"]\n'
    assert ids(clean) == {}


def test_an_env_that_reads_its_secret_from_outside_is_not_a_hardcoded_secret():
    assert "docker-secret-env" not in ids("FROM alpine:3.20\nARG API_TOKEN=${API_TOKEN}\nRUN true\n")


def test_a_database_open_to_the_internet_is_found_in_terraform():
    assert ids('resource "aws_db_instance" "m" {\n  publicly_accessible = true\n}\n').get("tf-public-db") == "high"
    assert "tf-public-db" not in ids('resource "aws_db_instance" "m" {\n  publicly_accessible = false\n}\n')


def test_a_node_jwt_with_the_none_algorithm_and_a_literal_secret_is_found():
    js = ("const jwt = require('jsonwebtoken');\n"
          "const t = jwt.verify(req.headers.authorization, 'secret', { algorithms: ['none', 'HS256'] });\n")
    found = ids(js)
    assert found.get("jwt-none") == "high" and found.get("jwt-hardcoded-secret") == "high"


def test_a_jwt_key_read_from_the_environment_is_not_a_literal_secret():
    js = "const t = jwt.verify(token, process.env.JWT_KEY, { algorithms: ['HS256'] });\n"
    assert "jwt-hardcoded-secret" not in ids(js) and "jwt-none" not in ids(js)


def test_user_input_in_an_argument_list_stays_a_lead_not_a_high_finding():
    guarded = ('import subprocess\nfrom flask import request, abort\nOK = {"a"}\n'
               'def ping():\n    host = request.args.get("host", "")\n    if host not in OK:\n        abort(400)\n'
               '    subprocess.run(["ping", "-c", "1", host], check=True)\n')
    assert ids(guarded, "a.py").get("subprocess-argv") == "medium"
    shell = 'import os\nfrom flask import request\ndef ping():\n    os.system("ping " + request.args.get("host"))\n'
    assert ids(shell, "a.py").get("cmd-injection-py") == "high"