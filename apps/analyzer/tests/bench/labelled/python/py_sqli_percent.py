import psycopg2
from flask import Flask, request

app = Flask(__name__)


@app.route("/order")
def order():
    order_id = request.args["id"]
    cur = psycopg2.connect("dbname=shop").cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s" % order_id)
    return {"order": cur.fetchone()}
