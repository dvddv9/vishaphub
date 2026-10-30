import express, { Request, Response } from "express";

const app = express();

app.get("/welcome", (req: Request, res: Response) => {
  const name = String(req.query.name ?? "");
  res.send(`<h1>Welcome, ${name}</h1>`);
});

app.listen(3000);
