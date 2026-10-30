const crypto = require("crypto");
const path = require("path");
const jwt = require("jsonwebtoken");

function newSessionId() {
  return crypto.randomBytes(32).toString("hex");
}

function verify(token) {
  return jwt.verify(token, process.env.JWT_SECRET, { algorithms: ["HS256"] });
}

function publicFile(name) {
  return path.join(__dirname, "public", path.basename(name));
}

module.exports = { newSessionId, verify, publicFile };
