import { Pool } from "pg";
import express, { Request, Response } from "express";

const pool = new Pool();
const app = express();

app.get("/accounts", async (req: Request, res: Response) => {
  const owner = String(req.query.owner ?? "");
  const { rows } = await pool.query("SELECT id, owner, balance FROM accounts WHERE owner = $1", [owner]);
  res.json(rows);
});

app.listen(3000);
