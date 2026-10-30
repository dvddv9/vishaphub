import subprocess
from flask import Flask, request

app = Flask(__name__)


@app.route("/thumb", methods=["POST"])
def thumb():
    filename = request.form["filename"]
    subprocess.run(f"convert {filename} -resize 128x128 thumb.png", shell=True, check=True)
    return "ok"
