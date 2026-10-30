from flask import Flask, abort, jsonify
from flask_login import current_user, login_required

from models import Invoice

app = Flask(__name__)


@app.route("/invoice/<int:invoice_id>")
@login_required
def invoice(invoice_id):
    inv = Invoice.query.get(invoice_id)
    if inv is None:
        abort(404)
    return jsonify(inv.to_dict())
