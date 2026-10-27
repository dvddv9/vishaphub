/**
 * Ready-made inputs for the "Try an example" buttons. Each one is small, runs
 * without an API key on the public demo, and shows a different kind of material
 * (Vishap is not only a code scanner).
 *
 * Nothing here is a real credential: the secrets are obvious placeholders.
 */

export interface Example {
  id: string;
  /** Short button label. */
  label: string;
  /** What the example shows, one line. */
  blurb: string;
  filename: string;
  material: string;
}

const SQLI = `import sqlite3

from flask import Flask, request

app = Flask(__name__)


@app.route("/user")
def user():
    name = request.args["name"]  # tainted: comes straight from the query string
    conn = sqlite3.connect("app.db")
    # SQL injection: the query is built by string formatting
    row = conn.execute(f"SELECT * FROM users WHERE name = '{name}'").fetchone()
    return {"user": row}
`;

const TERRAFORM = `resource "aws_s3_bucket" "uploads" {
  bucket = "acme-customer-uploads"
  acl    = "public-read"
}

resource "aws_security_group" "web" {
  name = "web"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "main" {
  engine              = "postgres"
  instance_class      = "db.t3.micro"
  username            = "admin"
  password            = "changeme123"
  publicly_accessible = true
  storage_encrypted   = false
  skip_final_snapshot = true
}
`;

const LOG = `2026-10-27 09:14:02 INFO  api  GET /health 200 2ms
2026-10-27 09:14:07 INFO  api  login ok user=anna@example.com ip=203.0.113.24
2026-10-27 09:14:11 WARN  api  GET /items?id=1' OR '1'='1 200 41ms ua="sqlmap/1.7"
2026-10-27 09:14:15 INFO  api  contact saved phone=+7 (916) 123-45-67
2026-10-27 09:14:19 ERROR db   connection retry db_password=Sup3rSecret! host=10.0.0.5:5432
2026-10-27 09:14:23 INFO  api  response headers Access-Control-Allow-Origin: *
2026-10-27 09:14:26 INFO  api  X-Forwarded-For: 198.51.100.7 trusted without proxy check
2026-10-27 09:14:31 INFO  api  GET /export 200 18:00:02 batch done
`;

const OPENAPI = `openapi: 3.0.3
info:
  title: Orders API
  version: 1.0.0
servers:
  - url: http://api.example.com
paths:
  /orders/{orderId}:
    get:
      summary: Get any order by id
      parameters:
        - name: orderId
          in: path
          required: true
          schema: { type: integer }
      responses:
        "200": { description: The order }
  /admin/export:
    post:
      summary: Export every customer record
      responses:
        "200": { description: CSV file }
  /orders:
    post:
      summary: Create an order
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                callback_url: { type: string }
                note: { type: string }
      responses:
        "201": { description: Created }
`;

export const EXAMPLES: Example[] = [
  {
    id: "sqli",
    label: "Python · SQL injection",
    blurb: "A Flask handler that builds a query from request data.",
    filename: "example_sqli.py",
    material: SQLI,
  },
  {
    id: "terraform",
    label: "Terraform · cloud config",
    blurb: "Public bucket, SSH open to the world, unencrypted database.",
    filename: "main.tf",
    material: TERRAFORM,
  },
  {
    id: "log",
    label: "app.log · leaks and attacks",
    blurb: "Personal data, a password and an injection attempt in a log.",
    filename: "app.log",
    material: LOG,
  },
  {
    id: "openapi",
    label: "OpenAPI · API spec",
    blurb: "No auth on admin routes, object ids in paths, plain HTTP.",
    filename: "openapi.yaml",
    material: OPENAPI,
  },
];

export function findExample(id: string | null | undefined): Example | undefined {
  if (!id) return undefined;
  return EXAMPLES.find((example) => example.id === id);
}
