"""Unit tests: PII redaction."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from callrecall import redact


class TestRedact(unittest.TestCase):
    def test_email(self):
        self.assertIn("[EMAIL]", redact.redact_text("reach me at sam@example.com ok?"))

    def test_phone_formats(self):
        for p in ["+1 (555) 123-4567", "555-123-4567", "5551234567", "+15551234567"]:
            self.assertIn("[PHONE]", redact.redact_text(f"call {p} now"), p)

    def test_phone_does_not_eat_years(self):
        self.assertIn("2026", redact.redact_text("in the year 2026 we met"))

    def test_address(self):
        out = redact.redact_text("I live at 742 Evergreen Terrace, Springfield")
        self.assertIn("[ADDRESS]", out)
        self.assertNotIn("742", out)

    def test_ssn_and_card(self):
        self.assertIn("[SSN]", redact.redact_text("ssn 123-45-6789"))
        self.assertIn("[CARD]", redact.redact_text("card 4111 1111 1111 1111"))

    def test_names(self):
        out = redact.redact_text("My neighbor John Smith said hi")
        self.assertIn("[NAME]", out)
        self.assertNotIn("John Smith", out)

    def test_names_skips_days(self):
        out = redact.redact_text("See you on Monday morning")
        self.assertIn("Monday", out)

    def test_toggles(self):
        out = redact.redact_text("sam@example.com", email=False)
        self.assertIn("sam@example.com", out)

    def test_empty(self):
        self.assertEqual(redact.redact_text(""), "")


if __name__ == "__main__":
    unittest.main()
