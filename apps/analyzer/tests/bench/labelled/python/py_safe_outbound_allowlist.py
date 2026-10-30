from urllib.parse import urlparse

import requests
from flask import Flask, abort, render_template, request

app = Flask(__name__)
ALLOWED_HOSTS = {"api.partner.example", "cdn.partner.example"}


@app.route("/preview")
def preview():
    url = request.args["url"]
    if urlparse(url).hostname not in ALLOWED_HOSTS:
        abort(400)
    resp = requests.get(url, timeout=5)
    return render_template("preview.html", body=resp.text[:2000])
