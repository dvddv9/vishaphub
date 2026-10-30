import jwt from "jsonwebtoken";

const JWT_SECRET = "changeme-supersecret-123";

export function sign(userId: string): string {
  return jwt.sign({ sub: userId }, JWT_SECRET, { algorithm: "HS256", expiresIn: "1h" });
}
