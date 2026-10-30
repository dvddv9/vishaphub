import ipaddress
import subprocess
from flask import Flask, abort, request

app = Flask(__name__)


@app.route("/ping")
def ping():
    try:
        host = str(ipaddress.ip_address(request.args.get("host", "127.0.0.1")))
    except ValueError:
        abort(400)
    result = subprocess.run(["ping", "-c", "1", host], capture_output=True, timeout=5, check=False)
    return {"reachable": result.returncode == 0}
