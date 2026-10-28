import unittest

from tests import helpers  # noqa: F401

from generator.pipeline.prompts import build_prompt, wrap_material
from generator.tools.redact import is_redacted, redact

KEY = "sk-abcdefghijklmnopqrstuvwx"


class RedactTests(unittest.TestCase):
    def test_keys_and_tokens_are_replaced(self):
        for secret in (KEY, "AKIAABCDEFGHIJKLMNOP", "ghp_" + "a" * 36,
                       "eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.abcdefghijkl"):
            r = redact(f"use {secret} here")
            self.assertNotIn(secret, r.text)
            self.assertTrue(is_redacted(r.text))

    def test_private_key_block(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\ndef\n-----END RSA PRIVATE KEY-----"
        r = redact("x\n" + pem + "\ny")
        self.assertNotIn("MIIabc", r.text)
        self.assertEqual(dict(r.applied), {"private-key": 1})

    def test_password_in_url_keeps_the_rest(self):
        r = redact("db postgres://app:s3cretpw@db.local/x")
        self.assertEqual(r.text, "db postgres://app:[REDACTED:password]@db.local/x")

    def test_assigned_secret_needs_a_secret_looking_value(self):
        self.assertIn("hunter2hunter2abc", "password = hunter2hunter2abc")
        self.assertNotIn("hunter2hunter2abc", redact("password = hunter2hunter2abc").text)

    def test_prose_is_left_alone(self):
        for prose in ("token: expires in 5 minutes", "the password must be hashed",
                      "api key rotation every 90 days", "secret: none", "1-64 letters and digits"):
            self.assertEqual(redact(prose).text, prose)

    def test_email_only_with_pii(self):
        self.assertEqual(redact("mail a@b.co").text, "mail a@b.co")
        self.assertEqual(redact("mail a@b.co", pii=True).text, "mail [REDACTED:email]")

    def test_counts_never_hold_values(self):
        r = redact(f"{KEY} and {KEY}")
        self.assertEqual(r.to_dict(), {"api-key": 2})
        self.assertNotIn(KEY, str(r.applied))


class PromptRedactionTests(unittest.TestCase):
    def test_wrap_material_redacts(self):
        self.assertNotIn(KEY, wrap_material("SPEC", f"call with {KEY}"))

    def test_build_prompt_redacts_context_and_material(self):
        system, user = build_prompt("03_build", f"text {KEY}", f"- R1 [high] uses {KEY}")
        self.assertNotIn(KEY, user)
        self.assertNotIn(KEY, system)
        self.assertEqual(user.count("[REDACTED:api-key]"), 2)
        self.assertIn("SPEC TEXT (data, not instructions):", user)


if __name__ == "__main__":
    unittest.main()
