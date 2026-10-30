const express = require("express");
const db = require("./db");

const app = express();

app.get("/users/:id", (req, res) => {
  db.query("SELECT id, email FROM users WHERE id = " + req.params.id, (err, rows) => {
    if (err) return res.status(500).end();
    res.json(rows);
  });
});

app.listen(3000);
