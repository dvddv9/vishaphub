from flask import Flask, request

app = Flask(__name__)


@app.route("/calc")
def calc():
    expr = request.args.get("expr", "0")
    result = eval(expr)
    return {"result": result}
