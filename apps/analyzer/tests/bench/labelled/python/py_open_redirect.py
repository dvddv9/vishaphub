from flask import Flask, redirect, request

app = Flask(__name__)


@app.route("/after-login")
def after_login():
    return redirect(request.args.get("next", "/"))
