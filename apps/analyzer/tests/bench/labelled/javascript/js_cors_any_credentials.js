const cors = require("cors");
const express = require("express");

const app = express();
app.use(cors({ origin: "*", credentials: true }));

app.get("/api/profile", (req, res) => res.json({ user: req.user }));

app.listen(3000);
