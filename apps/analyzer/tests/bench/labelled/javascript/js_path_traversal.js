const fs = require("fs");
const path = require("path");
const express = require("express");

const app = express();

app.get("/files/:name", (req, res) => {
  fs.readFile(path.join(__dirname, "public", req.params.name), (err, data) => {
    if (err) return res.status(404).end();
    res.send(data);
  });
});

app.listen(3000);
