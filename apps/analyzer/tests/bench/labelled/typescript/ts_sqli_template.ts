import { Pool } from "pg";
import express, { Request, Response } from "express";

const pool = new Pool();
const app = express();

app.get("/accounts", async (req: Request, res: Response) => {
  const owner = String(req.query.owner ?? "");
  const { rows } = await pool.query(`SELECT * FROM accounts WHERE owner = '${owner}'`);
  res.json(rows);
});

app.listen(3000);
