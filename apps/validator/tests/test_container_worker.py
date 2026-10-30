"""Hostile code in a real worker container. Needs Docker and a built worker image.

    docker build -t vishap-validator:worker apps/validator
    VISHAP_TEST_WORKER_IMAGE=vishap-validator:worker pytest apps/validator/tests/test_container_worker.py

Every probe below is a test the *submitted* code runs. It passes only when the escape fails, so a
PASS verdict from the worker means every one of them was blocked, and any escape shows up as a
failed test, hence a FAIL verdict. CI runs this on Linux; where it is not set up the tests skip.
"""
import json
import os
import shutil
import subprocess

import pytest

from validator.container import run_in_container

IMAGE = os.getenv("VISHAP_TEST_WORKER_IMAGE", "")
DOCKER = shutil.which("docker")
CANARY = "vishap-canary-do-not-leak-7f3a"

pytestmark = pytest.mark.skipif(not (IMAGE and DOCKER), reason="no Docker or VISHAP_TEST_WORKER_IMAGE")

HOSTILE = {
    "test_network.py": '''
import socket
import pytest

def test_tcp_is_refused():
    with pytest.raises(OSError):
        socket.create_connection(("1.1.1.1", 443), timeout=2)

def test_dns_is_refused():
    with pytest.raises(OSError):
        socket.getaddrinfo("example.com", 443)
''',
    "test_native_socket.py": '''
import ctypes, socket, struct

def test_a_native_connect_that_skips_the_python_guard_fails():
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.socket(2, 1, 0)
    assert fd >= 0
    addr = struct.pack("=H", 2) + struct.pack(">H", 443) + socket.inet_aton("1.1.1.1") + b"\\0" * 8
    assert libc.connect(fd, addr, len(addr)) == -1
''',
    "test_child_process.py": '''
import subprocess, sys

def test_a_child_python_without_the_guard_cannot_connect():
    code = "import socket; socket.create_connection(('1.1.1.1', 443), 2)"
    out = subprocess.run([sys.executable, "-S", "-E", "-c", code], capture_output=True, timeout=20)
    assert out.returncode != 0

def test_the_process_count_is_capped():
    procs = []
    try:
        for _ in range(300):
            procs.append(subprocess.Popen(["sleep", "5"]))
    except OSError:
        pass
    finally:
        for p in procs:
            p.kill()
    assert len(procs) < 300
''',
    "test_secrets_and_files.py": '''
import os

CANARY = "@@CANARY@@"

def test_the_canary_is_not_in_the_environment():
    assert CANARY not in "".join(os.environ.values())

def test_the_parent_process_environment_does_not_hold_it():
    try:
        data = open(f"/proc/{os.getppid()}/environ", "rb").read().decode("utf-8", "replace")
    except OSError:
        return
    assert CANARY not in data

def test_the_image_and_root_are_read_only():
    for path in ("/app/x", "/etc/x", "/x"):
        try:
            open(path, "w").write("x")
        except OSError:
            continue
        raise AssertionError(path + " was writable")

def test_a_file_bigger_than_the_scratch_space_cannot_be_written():
    try:
        with open("/tmp/big", "wb") as fh:
            for _ in range(200):
                fh.write(b"0" * 1024 * 1024)
    except OSError:
        return
    raise AssertionError("200 MB fitted in a 32 MB scratch")
'''.replace('@@CANARY@@', CANARY),
}


@pytest.fixture()
def hostile(tmp_path):
    for name, body in HOSTILE.items():
        (tmp_path / name).write_text(body.lstrip("\n"), encoding="utf-8")
    return tmp_path, {"tests": list(HOSTILE)}


def test_hostile_code_is_blocked_and_the_run_says_which_isolation_held(hostile):
    root, spec = hostile
    result = run_in_container(str(root), spec, image=IMAGE, timeout=180, extra_env={})
    assert result["ok"], result["error"]
    report = result["report"]
    behavior = next(c for c in report["checks"] if c["name"] == "behavior")
    failed = [f["message"] for f in behavior["findings"]]
    assert report["verdict"] == "PASS", failed
    assert "network: container" in (behavior.get("note") or "")
    assert result["cleanup_confirmed"] is True


def test_a_worker_without_the_network_cut_off_refuses_to_run_anything(tmp_path):
    marker = tmp_path / "ran.txt"
    (tmp_path / "test_x.py").write_text(
        "import os\nopen('/tmp/ran', 'w').write('x')\n\ndef test_x():\n    pass\n", encoding="utf-8")
    tmp_path.chmod(0o755)
    for item in tmp_path.iterdir():
        item.chmod(0o644)
    # Same image, same worker, but started with a network: it must see that and run nothing.
    out = subprocess.run(
        [DOCKER, "run", "--rm", "--read-only", "--tmpfs", "/tmp:size=16m",
         "--mount", f"type=bind,source={tmp_path},target=/in,readonly",
         "-e", "VISHAP_VALIDATOR_ISOLATION=container", "--entrypoint", "sh", IMAGE, "-c",
         "echo '{\"tests\":[\"test_x.py\"]}' > /tmp/spec.json && python -m validator.worker /in /tmp/spec.json"],
        capture_output=True, text=True, timeout=120, check=False)
    line = next(ln for ln in out.stdout.splitlines() if ln.startswith("VISHAP_REPORT:"))
    report = json.loads(line[len("VISHAP_REPORT:"):])
    assert report["verdict"] == "FAIL"
    assert "did not confirm" in report["reason"]
    assert not marker.exists()

def test_a_secret_handed_to_the_worker_stops_it_before_any_code_runs(hostile):
    root, spec = hostile
    result = run_in_container(str(root), spec, image=IMAGE, timeout=120,
                              extra_env={"CANARY_API_KEY": CANARY})
    assert result["ok"], result["error"]
    report = result["report"]
    assert report["verdict"] == "FAIL"
    assert "CANARY_API_KEY" in report["reason"] and CANARY not in json.dumps(report)
    assert result["cleanup_confirmed"] is True

VULN_FILES = {
    "app.py": "def find(cur, name):\n    cur.execute(\"select id from users where name = '\" + name + \"'\")\n    return cur.fetchall()\n",
    "p.py": "import os\n\n\ndef read(base, name):\n    with open(os.path.join(base, name), encoding='utf-8') as fh:\n        return fh.read()\n",
    "c.py": "import os\n\n\ndef echo(text):\n    os.system('echo ' + text)\n",
}
TARGETS = [
    {"class": "sqli", "entry": "app:find", "args": ["$cursor", "$payload"]},
    {"class": "path_traversal", "entry": "p:read", "args": ["$base", "$payload"]},
    {"class": "command_injection", "entry": "c:echo", "args": ["$payload"]},
]


def test_the_trusted_exploit_probes_run_in_the_worker_and_reproduce_all_three_attacks(tmp_path):
    for name, body in VULN_FILES.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    result = run_in_container(str(tmp_path), {"exploit_targets": TARGETS}, image=IMAGE, mode="exploits", timeout=120)
    assert result["ok"], result["error"]
    assert result["report"]["refused"] == ""
    assert [r["result"] for r in result["report"]["exploits"]] == ["reproduced"] * 3
    assert result["cleanup_confirmed"] is True


def test_the_exploit_mode_refuses_when_the_worker_is_not_cut_off_from_the_network(tmp_path):
    for name, body in VULN_FILES.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    tmp_path.chmod(0o755)
    for item in tmp_path.iterdir():
        item.chmod(0o644)
    (tmp_path / "spec.json").write_text(json.dumps({"exploit_targets": TARGETS}), encoding="utf-8")
    (tmp_path / "spec.json").chmod(0o644)
    out = subprocess.run(
        [DOCKER, "run", "--rm", "--read-only", "--tmpfs", "/tmp:size=16m",
         "--mount", f"type=bind,source={tmp_path},target=/in,readonly",
         "-e", "VISHAP_VALIDATOR_ISOLATION=container", "--entrypoint", "python", IMAGE,
         "-m", "validator.worker", "/in", "/in/spec.json", "--exploits"],
        capture_output=True, text=True, timeout=120, check=False)
    line = next(ln for ln in out.stdout.splitlines() if ln.startswith("VISHAP_EXPLOITS:"))
    answer = json.loads(line[len("VISHAP_EXPLOITS:"):])
    assert answer["exploits"] == [] and "did not confirm" in answer["refused"]