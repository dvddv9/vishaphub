const https = require("https");
const axios = require("axios");

const agent = new https.Agent({ rejectUnauthorized: false });

async function fetchAccount(token) {
  const res = await axios.get("https://accounts.internal.example.com/me", {
    httpsAgent: agent,
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.data;
}

module.exports = { fetchAccount };
