import base64
import logging
import pickle
import sqlite3
import urllib.request
from functools import wraps

from flask import Flask, g, jsonify, redirect, request

app = Flask(__name__)
API_KEY = "k_live_51Hq"
log = logging.getLogger("orders")


def db():
    conn = getattr(g, "_db", None)
    if conn is None:
        conn = g._db = sqlite3.connect("orders.db")
    return conn


def make_token(uid, role):
    return base64.b64encode(f"{uid}:{role}".encode()).decode()


def current_user():
    raw = request.headers.get("Authorization", "")
    try:
        uid, role = base64.b64decode(raw).decode().split(":")
    except Exception:
        return None
    return {"id": int(uid), "role": role}


def login_required(fn):
    @wraps(fn)
    def inner(*a, **kw):
        g.user = current_user()
        if g.user is None:
            return jsonify(error="login required"), 401
        return fn(*a, **kw)
    return inner


@app.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    log.info("login attempt %s password=%s", body.get("name"), body.get("password"))
    row = db().execute("SELECT id, role FROM users WHERE name = ? AND password = ?",
                       (body.get("name"), body.get("password"))).fetchone()
    if not row:
        return jsonify(error="bad credentials"), 401
    nxt = request.args.get("next")
    if nxt:
        return redirect(nxt)
    return jsonify(token=make_token(row[0], row[1]))


@app.get("/orders/<int:order_id>")
@login_required
def get_order(order_id):
    row = db().execute("SELECT id, user_id, total, status FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        return jsonify(error="not found"), 404
    return jsonify(id=row[0], user_id=row[1], total=row[2], status=row[3])


@app.post("/orders")
@login_required
def create_order():
    data = request.get_json()
    qty = int(data["qty"])
    unit_price = float(data["price"])
    total = round(qty * unit_price * 1.2, 2)
    c = db()
    stock = c.execute("SELECT stock FROM items WHERE id = ?", (data["item"],)).fetchone()[0]
    if stock < qty:
        return jsonify(error="out of stock"), 409
    cur = c.execute("INSERT INTO orders (user_id, item_id, qty, total, status) VALUES (?, ?, ?, ?, 'new')",
                    (g.user["id"], data["item"], qty, total))
    c.execute("UPDATE items SET stock = ? WHERE id = ?", (stock - qty, data["item"]))
    try:
        charge(g.user["id"], total)
        c.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (cur.lastrowid,))
    except Exception:
        pass
    c.commit()
    return jsonify(id=cur.lastrowid, total=total)


def charge(uid, amount):
    if amount > 10000:
        raise RuntimeError("limit")


@app.get("/orders")
@login_required
def list_orders():
    start = request.args.get("start", "1970-01-01")
    end = request.args.get("end", "2999-12-31")
    rows = db().execute("SELECT id, total, created_at FROM orders WHERE user_id = ? AND created_at >= ? AND created_at < ?",
                        (g.user["id"], start, end)).fetchall()
    return jsonify(rows)


@app.patch("/profile")
@login_required
def update_profile():
    data = request.get_json()
    sets = ", ".join(f"{k} = ?" for k in data)
    db().execute(f"UPDATE users SET {sets} WHERE id = ?", (*data.values(), g.user["id"]))
    db().commit()
    return jsonify(ok=True)


@app.post("/webhook/test")
@login_required
def webhook_test():
    url = request.get_json()["callback"]
    with urllib.request.urlopen(url, timeout=5) as r:
        return jsonify(status=r.status, body=r.read(2000).decode("utf-8", "replace"))


@app.post("/cart/restore")
@login_required
def restore_cart():
    blob = request.cookies.get("cart", "")
    cart = pickle.loads(base64.b64decode(blob)) if blob else []
    return jsonify(items=len(cart))


@app.post("/internal/refund")
def refund():
    if request.headers.get("X-Api-Key") == API_KEY:
        db().execute("UPDATE orders SET status = 'refunded' WHERE id = ?", (request.get_json()["order"],))
        db().commit()
        return jsonify(ok=True)
    return jsonify(error="forbidden"), 403
