import base64
import pickle
from flask import Flask, request

app = Flask(__name__)


@app.route("/me")
def me():
    raw = request.cookies.get("session", "")
    session = pickle.loads(base64.b64decode(raw))
    return {"user": session.get("user")}
