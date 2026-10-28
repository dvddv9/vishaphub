"""Example specs for the web form ("Start with an example").

Each one is a complete spec.yaml; tests load every one of them through
the real loader. `{today}` is replaced with today's date so the example
is not stale on first run.
"""

from __future__ import annotations

import datetime as dt

EXAMPLES = (
    {
        "id": "user-lookup",
        "title": "User lookup",
        "description": "A public endpoint, no open gaps. Start here.",
        "spec": """\
version: 1
updated: {today}

text: |
  Add an HTTP endpoint GET /user that returns one user by name
  from the app database. Called by the public web app, without sign-in.

target: python/flask
kind: http-endpoint
output: handlers/user.py
caller: public
route: GET /user

inputs:
  - name: name
    in: query
    rule: "1-64 letters and digits"

outputs:
  - status: 200
    body: "json: id, name only"
  - status: 404
    when: "no such user"
  - status: 400
    when: "invalid name"

profile: owasp-asvs-2
constraints: [include-tests, validate-inputs]

must_never:
  - id: sql-from-input
    text: "SQL is never built from the input"
  - id: log-raw-input
    text: "Raw input is never logged"

check: analyzer
""",
    },
    {
        "id": "with-a-gap",
        "title": "A spec with a gap",
        "description": "No answer for invalid input: Design reports a critical gap and --gate blocks.",
        "spec": """\
version: 1
updated: {today}

text: |
  Add an HTTP endpoint GET /user that returns one user by name
  from the app database. Called by the public web app, without sign-in.

target: python/flask
kind: http-endpoint
output: handlers/user.py
caller: public
route: GET /user

inputs:
  - name: name
    in: query
    rule: "1-64 letters and digits"

outputs:
  - status: 200
    body: "json: id, name only"
  - status: 404
    when: "no such user"

profile: owasp-asvs-2
constraints: [include-tests, validate-inputs]

must_never:
  - id: sql-from-input
    text: "SQL is never built from the input"
  - id: log-raw-input
    text: "Raw input is never logged"

check: analyzer
""",
    },
    {
        "id": "order-signed-in",
        "title": "Order lookup, signed in",
        "description": "An endpoint for signed-in users: the auth measure and a numeric id.",
        "spec": """\
version: 1
updated: {today}

text: |
  Add an HTTP endpoint GET /order that returns one order of the signed-in
  customer by its number. Orders of other customers must not be readable.

target: python/flask
kind: http-endpoint
output: handlers/order.py
caller: signed-in
route: GET /order

inputs:
  - name: number
    in: query
    rule: "1-12 digits"

outputs:
  - status: 200
    body: "json: number, status, total"
  - status: 404
    when: "no such order for this customer"
  - status: 400
    when: "invalid number"

profile: owasp-asvs-2
constraints: [include-tests, validate-inputs]

must_never:
  - id: sql-from-input
    text: "SQL is never built from the input"
  - id: log-raw-input
    text: "Raw input is never logged"

check: analyzer
""",
    },
    {
        "id": "create-user-json",
        "title": "Create user (JSON body)",
        "description": "A POST with the value in a JSON body: Verify attacks body fields as it does query values.",
        "spec": """\
version: 1
updated: {today}

text: |
  Add an HTTP endpoint POST /user that creates one user from a JSON body
  {{"username": "..."}}. Called by signed-in users; a name that is taken is refused.

target: python/flask
kind: http-endpoint
output: handlers/create_user.py
caller: signed-in
route: POST /user

inputs:
  - name: username
    in: body
    rule: "3-32 letters and digits"

outputs:
  - status: 201
    body: "json: id, username only"
  - status: 400
    when: "invalid username"
  - status: 401
    when: "no valid session"
  - status: 409
    when: "username is taken"

profile: owasp-asvs-2
constraints: [include-tests, validate-inputs]

must_never:
  - id: sql-from-input
    text: "SQL is never built from the input"
  - id: log-raw-input
    text: "Raw input is never logged"

should:
  - id: audit-create
    text: "Every created user is written to the audit log"

check: analyzer
""",
    },
    {
        "id": "item-by-path",
        "title": "Item by path",
        "description": "The value is part of the route (GET /item/<id>): Verify fills the placeholder.",
        "spec": """\
version: 1
updated: {today}

text: |
  Add an HTTP endpoint GET /item/<id> that returns one item by its numeric id.
  Called by the public web app, without sign-in.

target: python/flask
kind: http-endpoint
output: handlers/item.py
caller: public
route: GET /item/<id>

inputs:
  - name: id
    in: path
    rule: "1-12 digits"

outputs:
  - status: 200
    body: "json: id, title only"
  - status: 404
    when: "no such item"
  - status: 400
    when: "invalid id"

profile: owasp-asvs-2
constraints: [include-tests, validate-inputs]

must_never:
  - id: sql-from-input
    text: "SQL is never built from the input"
  - id: log-raw-input
    text: "Raw input is never logged"

check: analyzer
""",
    },
)


def examples(today: dt.date | None = None) -> list[dict]:
    day = (today or dt.date.today()).isoformat()
    return [{**e, "spec": e["spec"].format(today=day)} for e in EXAMPLES]
