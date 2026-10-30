from pathlib import Path
from flask import Flask, abort, request

app = Flask(__name__)
UPLOAD_DIR = Path("/srv/uploads").resolve()


@app.route("/download")
def download():
    target = (UPLOAD_DIR / Path(request.args["name"]).name).resolve()
    if UPLOAD_DIR not in target.parents:
        abort(404)
    return target.read_bytes()
