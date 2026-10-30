const express = require("express");

const app = express();
app.use(express.json());

app.post("/run", (req, res) => {
  const result = eval(req.body.code);
  res.json({ result });
});

app.listen(3000);
