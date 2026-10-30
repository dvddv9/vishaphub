import sqlite3
from flask import Flask, request
from flask_login import login_required

app = Flask(__name__)


@app.route("/user")
@login_required
def user():
    name = request.args.get("name", "")
    db = sqlite3.connect("app.db")
    row = db.execute("SELECT id, email FROM users WHERE name = ?", (name,)).fetchone()
    return {"user": row}
