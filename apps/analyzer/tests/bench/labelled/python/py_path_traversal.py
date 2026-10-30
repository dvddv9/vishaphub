import os
from flask import Flask, request

app = Flask(__name__)
UPLOAD_DIR = "/srv/uploads"


@app.route("/download")
def download():
    name = request.args["name"]
    with open(os.path.join(UPLOAD_DIR, name), "rb") as fh:
        return fh.read()
