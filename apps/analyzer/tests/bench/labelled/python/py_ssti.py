from flask import Flask, render_template_string, request

app = Flask(__name__)


@app.route("/banner")
def banner():
    text = request.args.get("text", "")
    return render_template_string("<p>" + text + "</p>")
