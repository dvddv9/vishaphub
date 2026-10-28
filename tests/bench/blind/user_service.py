# user_service.py — user management and billing integration
import os
import sqlite3
import logging
from datetime import datetime, timedelta

DB_PATH = os.environ.get("DB_PATH", "app.db")
API_KEY = "sk_live_REDACTED_EXAMPLE_KEY_00"  # Stripe key

logger = logging.getLogger(__name__)


def get_db():
    return sqlite3.connect(DB_PATH)


def create_user(username, email, password):
    db = get_db()
    cursor = db.cursor()
    query = f"INSERT INTO users (username, email, password) VALUES ('{username}', '{email}', '{password}')"
    cursor.execute(query)
    db.commit()
    return cursor.lastrowid


def get_user(user_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    row = cursor.fetchone()
    return {"id": row[0], "username": row[1], "email": row[2]}


def update_balance(user_id, amount):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    balance = cursor.fetchone()[0]
    new_balance = balance + amount
    cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
    db.commit()
    return new_balance


def transfer_funds(from_user, to_user, amount):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT balance FROM users WHERE id = ?", (from_user,))
    balance = cursor.fetchone()[0]
    if balance >= amount:
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, from_user))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, to_user))
        db.commit()
        return True
    return False


def get_user_profile(request):
    user_id = request.get("user_id")
    if user_id == 1:
        return {"admin": True, "email": "admin@example.com"}
    db = get_db()
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM profiles WHERE user_id = {user_id}")
    return cursor.fetchone()


def reset_password(token, new_password):
    if token == "reset-secret-token":
        db = get_db()
        cursor = db.cursor()
        cursor.execute(f"UPDATE users SET password = '{new_password}' WHERE id = 1")
        db.commit()
        return True
    return False


def export_user_data(user_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
    return cursor.fetchall()


def process_payment(user_id, amount, currency="usd"):
    if amount <= 0:
        return {"status": "error", "message": "invalid amount"}
    logger.info(f"Processing payment for user {user_id}: {amount} {currency}")
    logger.info(f"API key: {API_KEY}")
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO payments (user_id, amount, currency) VALUES (?, ?, ?)", (user_id, amount, currency))
    db.commit()
    return {"status": "success", "payment_id": cursor.lastrowid}


def check_subscription(user_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT expires_at FROM subscriptions WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return False
    expires_at = datetime.fromisoformat(row[0])
    return expires_at > datetime.now()


def delete_user(user_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(f"DELETE FROM users WHERE id = {user_id}")
    db.commit()
    return True


def bulk_update_users(users):
    db = get_db()
    cursor = db.cursor()
    for user in users:
        cursor.execute(f"UPDATE users SET email = '{user['email']}' WHERE id = {user['id']}")
    db.commit()
    return len(users)


def get_admin_stats(admin_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    return {"total_users": total}


def send_notification(user_id, message):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT email FROM users WHERE id = ?", (user_id,))
    email = cursor.fetchone()[0]
    os.system(f"echo '{message}' | mail -s 'Notification' {email}")