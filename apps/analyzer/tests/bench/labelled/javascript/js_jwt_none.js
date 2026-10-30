const jwt = require("jsonwebtoken");

function authenticate(req, res, next) {
  const token = (req.headers.authorization || "").replace("Bearer ", "");
  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET, { algorithms: ["none", "HS256"] });
    next();
  } catch (err) {
    res.status(401).end();
  }
}

module.exports = authenticate;
