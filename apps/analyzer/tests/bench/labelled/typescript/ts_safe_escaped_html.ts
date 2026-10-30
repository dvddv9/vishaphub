import express, { Request, Response } from "express";

const app = express();

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}

app.get("/welcome", (req: Request, res: Response) => {
  res.send(`<h1>Welcome, ${escapeHtml(String(req.query.name ?? ""))}</h1>`);
});

app.listen(3000);
