import os, sqlite3, hashlib, time
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)
SECRET_KEY = "dev-secret-123"
UPLOAD_DIR = "/srv/uploads"
_cache = {}

def db():
    return sqlite3.connect("shop.db")

@app.get("/user")
def get_user():
    name = request.args.get("name", "")
    row = db().execute(f"SELECT id, email FROM users WHERE name = '{name}'").fetchone()
    return jsonify(row)

@app.get("/download")
def download():
    fname = request.args["file"]
    return send_file(os.path.join(UPLOAD_DIR, fname))

@app.post("/login")
def login():
    data = request.get_json()
    pw = hashlib.md5(data["password"].encode()).hexdigest()
    row = db().execute(
        "SELECT password FROM users WHERE name = ?", (data["name"],)
    ).fetchone()
    if row and row[0] == pw:
        return jsonify(token=hashlib.sha1((data["name"] + SECRET_KEY).encode()).hexdigest())
    return jsonify(error="bad credentials"), 401

@app.get("/items")
def items(page=0, size=20, seen=[]):
    page = int(request.args.get("page", page))
    size = int(request.args.get("size", size))
    rows = db().execute("SELECT id, title FROM items").fetchall()
    chunk = rows[page * size : page * size + size + 1]
    seen.extend(r[0] for r in chunk)
    return jsonify(chunk)

@app.post("/transfer")
def transfer():
    data = request.get_json()
    bal = db().execute("SELECT balance FROM accounts WHERE id=?", (data["from"],)).fetchone()[0]
    if bal >= data["amount"]:
        c = db()
        c.execute("UPDATE accounts SET balance = balance - ? WHERE id=?", (data["amount"], data["from"]))
        c.execute("UPDATE accounts SET balance = balance + ? WHERE id=?", (data["amount"], data["to"]))
        c.commit()
        return jsonify(ok=True)
    return jsonify(ok=False)

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
