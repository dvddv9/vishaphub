import sqlite3
from flask import Flask, request

app = Flask(__name__)


@app.route("/user")
def user():
    name = request.args.get("name", "")
    db = sqlite3.connect("app.db")
    row = db.execute(f"SELECT id, email FROM users WHERE name = '{name}'").fetchone()
    return {"user": row}
