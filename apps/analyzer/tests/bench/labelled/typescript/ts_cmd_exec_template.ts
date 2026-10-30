import { exec } from "child_process";
import express, { Request, Response } from "express";

const app = express();

app.get("/dns", (req: Request, res: Response) => {
  const domain = String(req.query.domain ?? "");
  exec(`nslookup ${domain}`, (err, stdout) => {
    res.type("text").send(stdout);
  });
});

app.listen(3000);
