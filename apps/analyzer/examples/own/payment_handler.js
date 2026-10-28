// Payment handler
const express = require("express");
const router = express.Router();

let balance = {};

// BUG 1: prototype pollution via merge
function merge(target, source) {
  for (const key in source) {
    if (typeof source[key] === "object") {
      target[key] = merge(target[key] || {}, source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

router.post("/pay", async (req, res) => {
  const userId = req.body.userId;
  const amount = req.body.amount;

  // BUG 2: race condition — read-then-write without lock
  const current = balance[userId] || 0;
  await new Promise(r => setTimeout(r, 100));
  balance[userId] = current - amount;

  // BUG 3: no validation of amount (negative allowed)
  res.json({ balance: balance[userId] });
});

router.post("/merge", (req, res) => {
  const user = {};
  // BUG 4: __proto__ pollution
  merge(user, req.body);
  res.json(user);
});

module.exports = router;
