import psycopg2

DB_HOST = "db.internal"
DB_PASSWORD = "Sup3rS3cret-2024"


def connect():
    return psycopg2.connect(host=DB_HOST, user="app", password=DB_PASSWORD, dbname="shop")
