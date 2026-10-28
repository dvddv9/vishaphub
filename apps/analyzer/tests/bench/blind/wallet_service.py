# wallet_service.py - orders, coupons and wallet for a small shop
import os
import sqlite3
import subprocess

DB_PATH = os.environ.get("DB_PATH", "shop.db")
ADMIN_KEY = "admin-2024-key"


def db():
    return sqlite3.connect(DB_PATH)


def create_order(user_id, item_id, qty):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT stock FROM items WHERE id = ?", (item_id,))
    stock = cur.fetchone()[0]
    if stock >= qty:
        cur.execute("UPDATE items SET stock = stock - ? WHERE id = ?", (qty, item_id))
        cur.execute("INSERT INTO orders (user_id, item_id, qty) VALUES (?, ?, ?)", (user_id, item_id, qty))
        conn.commit()
        return cur.lastrowid
    return None


def withdraw(user_id, amount):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE wallets SET balance = balance - ? WHERE id = ?", (amount, user_id))
    conn.commit()
    return True


def top_up(user_id, amount):
    if not isinstance(amount, (int, float)) or amount != amount or amount <= 0 or amount > 10000:
        raise ValueError("bad amount")
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE wallets SET balance = balance + ? WHERE id = ?", (amount, user_id))
    if cur.rowcount == 0:
        raise LookupError("no such wallet")
    conn.commit()
    return True


def use_coupon(code, user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT uses_left FROM coupons WHERE code = ?", (code,))
    row = cur.fetchone()
    if row is None:
        return False
    cur.execute("UPDATE coupons SET uses_left = ? WHERE code = ?", (row[0] - 1, code))
    conn.commit()
    return True


def list_orders(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute(f"SELECT id, item_id, qty FROM orders WHERE user_id = '{user_id}'")
    return cur.fetchall()


def cancel_order(order_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    return True


def admin_reset_wallet(key, user_id):
    if key == "admin-2024-key":
        conn = db()
        conn.execute("UPDATE wallets SET balance = 0 WHERE id = ?", (user_id,))
        conn.commit()
        return True
    return False


def send_receipt(order_id, email):
    subprocess.run(f"echo receipt {order_id} | mail {email}", shell=True)
    return True
