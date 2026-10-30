import json
import yaml
from flask import Flask, request
from flask_login import login_required

app = Flask(__name__)


@app.route("/import", methods=["POST"])
@login_required
def import_config():
    if request.mimetype == "application/json":
        config = json.loads(request.data)
    else:
        config = yaml.safe_load(request.data)
    return {"keys": sorted(config or {})}
