const { exec } = require("child_process");
const express = require("express");

const app = express();

app.get("/list", (req, res) => {
  exec("ls -la " + req.query.dir, (err, stdout) => {
    res.type("text").send(stdout);
  });
});

app.listen(3000);
