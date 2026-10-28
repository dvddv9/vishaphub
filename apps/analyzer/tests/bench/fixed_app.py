# The planted_app.py with every planted bug fixed. Benchmark input: must stay (nearly) silent and
# must close every exploit that worked on planted_app.py.
import hmac
import hashlib
import os
import secrets
import sqlite3
from flask import Flask, request, jsonify, send_from_directory, abort, session

app = Flask(__name__)
app.secret_key = os.environ["APP_SECRET_KEY"]
UPLOAD_DIR = "/srv/uploads"
MAX_PAGE = 100


def db():
    return sqlite3.connect("shop.db")


def login_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("uid"):
            abort(401)
        return fn(*a, **kw)
    return wrapper


@app.get("/user")
@login_required
def get_user():
    name = request.args.get("name", "")
    row = db().execute("SELECT id, email FROM users WHERE name = ?", (name,)).fetchone()
    return jsonify(row)


@app.get("/download")
@login_required
def download():
    return send_from_directory(UPLOAD_DIR, request.args["file"])


@app.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    name, password = data.get("name"), data.get("password")
    if not isinstance(name, str) or not isinstance(password, str):
        abort(400)
    row = db().execute("SELECT salt, hash FROM users WHERE name = ?", (name,)).fetchone()
    if row:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(row[0]), 200_000).hex()
        if hmac.compare_digest(digest, row[1]):
            session["uid"] = name
            return jsonify(token=secrets.token_urlsafe(32))
    return jsonify(error="bad credentials"), 401


@app.get("/items")
@login_required
def items():
    page = max(int(request.args.get("page", 0)), 0)
    size = min(max(int(request.args.get("size", 20)), 1), MAX_PAGE)
    rows = db().execute("SELECT id, title FROM items LIMIT ? OFFSET ?", (size, page * size)).fetchall()
    return jsonify(rows)


@app.post("/transfer")
@login_required
def transfer():
    data = request.get_json(silent=True) or {}
    amount = data.get("amount")
    if not isinstance(amount, int) or not (0 < amount <= 1_000_000):
        abort(400)
    c = db()
    cur = c.execute("UPDATE accounts SET balance = balance - ? WHERE id = ? AND balance >= ?",
                    (amount, data.get("from"), amount))
    if cur.rowcount != 1:
        c.rollback()
        return jsonify(ok=False), 409
    cur = c.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?", (amount, data.get("to")))
    if cur.rowcount != 1:
        c.rollback()
        return jsonify(ok=False), 404
    c.commit()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1")
