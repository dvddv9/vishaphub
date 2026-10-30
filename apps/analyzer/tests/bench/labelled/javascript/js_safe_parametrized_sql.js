const express = require("express");
const { Pool } = require("pg");

const pool = new Pool();
const app = express();

app.get("/users/:id", async (req, res) => {
  const { rows } = await pool.query("SELECT id, email FROM users WHERE id = $1", [req.params.id]);
  res.json(rows);
});

app.listen(3000);
