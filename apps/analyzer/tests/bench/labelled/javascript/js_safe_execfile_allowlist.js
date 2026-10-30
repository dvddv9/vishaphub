const { execFile } = require("child_process");
const express = require("express");

const app = express();
const ALLOWED = new Set(["reports", "exports"]);

app.get("/list", (req, res) => {
  if (!ALLOWED.has(req.query.dir)) return res.status(400).end();
  execFile("ls", ["-la", req.query.dir], (err, stdout) => {
    res.type("text").send(stdout);
  });
});

app.listen(3000);
