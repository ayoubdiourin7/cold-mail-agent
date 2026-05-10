import io
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import config
import email_validator
import main


class EmailValidatorTests(unittest.TestCase):
    def test_extract_mx_hosts_normalizes_and_sorts_hosts(self) -> None:
        mx_answers = [
            SimpleNamespace(preference=20, exchange="backup.example.com."),
            SimpleNamespace(preference=10, exchange="mx.example.com."),
        ]

        self.assertEqual(
            email_validator.extract_mx_hosts(mx_answers),
            ["mx.example.com", "backup.example.com"],
        )

    def test_validate_email_address_skips_domain_already_cached_as_invalid(self) -> None:
        with patch("email_validator.check_mail_domain") as mocked_domain_check:
            result = email_validator.validate_email_address(
                "jobs@example.com",
                known_invalid_domains={"example.com"},
            )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "known_invalid_domain")
        mocked_domain_check.assert_not_called()

    def test_validate_email_address_rejects_invalid_syntax(self) -> None:
        result = email_validator.validate_email_address("not-an-email")

        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "invalid_syntax")

    @patch("email_validator.check_mail_domain", return_value=(True, None))
    def test_validate_email_address_accepts_valid_syntax_and_mx(self, mocked_domain_check) -> None:
        result = email_validator.validate_email_address("Jobs@Example.com")

        self.assertTrue(result.is_valid)
        self.assertEqual(result.normalized_email, "jobs@example.com")
        mocked_domain_check.assert_called_once_with("example.com")

    @patch("email_validator.check_mail_domain", return_value=(False, "missing_domain"))
    def test_validate_email_address_reports_domain_failure(self, mocked_domain_check) -> None:
        result = email_validator.validate_email_address("jobs@example.com")

        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "missing_domain")
        mocked_domain_check.assert_called_once_with("example.com")

    @patch("email_validator.check_mail_domain", return_value=(False, "missing_domain"))
    def test_validate_email_address_persists_cacheable_invalid_domains(self, mocked_domain_check) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_domains_path = Path(temp_dir) / "invalid_email_domains.txt"
            known_invalid_domains: set[str] = set()

            result = email_validator.validate_email_address(
                "jobs@example.com",
                known_invalid_domains=known_invalid_domains,
                invalid_domains_path=invalid_domains_path,
            )

            self.assertFalse(result.is_valid)
            self.assertEqual(known_invalid_domains, {"example.com"})
            self.assertEqual(
                invalid_domains_path.read_text(encoding="utf-8"),
                "example.com\n",
            )

        mocked_domain_check.assert_called_once_with("example.com")

    @patch("email_validator.smtplib.SMTP")
    def test_has_responding_smtp_server_returns_true_when_one_host_responds(self, mocked_smtp) -> None:
        mocked_smtp.side_effect = [Exception("down"), mocked_smtp.return_value]

        self.assertTrue(
            email_validator.has_responding_smtp_server(["mx1.example.com", "mx2.example.com"])
        )
        self.assertEqual(mocked_smtp.call_count, 2)

    @patch("email_validator.smtplib.SMTP", side_effect=Exception("down"))
    def test_has_responding_smtp_server_returns_false_when_all_hosts_fail(self, mocked_smtp) -> None:
        self.assertFalse(
            email_validator.has_responding_smtp_server(["mx1.example.com", "mx2.example.com"])
        )
        self.assertEqual(mocked_smtp.call_count, 2)

    @patch("email_validator.has_responding_smtp_server", return_value=True)
    @patch("email_validator.dns.resolver.Resolver")
    def test_check_mail_domain_accepts_mx_with_responding_smtp(
        self,
        mocked_resolver_class,
        mocked_has_smtp,
    ) -> None:
        mocked_resolver = mocked_resolver_class.return_value
        mocked_resolver.resolve.return_value = [
            SimpleNamespace(preference=10, exchange="mx.example.com.")
        ]

        is_valid, reason = email_validator.check_mail_domain("example.com")

        self.assertTrue(is_valid)
        self.assertIsNone(reason)
        mocked_has_smtp.assert_called_once_with(["mx.example.com"])

    @patch("email_validator.has_responding_smtp_server", return_value=False)
    @patch("email_validator.dns.resolver.Resolver")
    def test_check_mail_domain_rejects_unresponsive_smtp(
        self,
        mocked_resolver_class,
        mocked_has_smtp,
    ) -> None:
        mocked_resolver = mocked_resolver_class.return_value
        mocked_resolver.resolve.return_value = [
            SimpleNamespace(preference=10, exchange="mx.example.com.")
        ]

        is_valid, reason = email_validator.check_mail_domain("example.com")

        self.assertFalse(is_valid)
        self.assertEqual(reason, "smtp_unreachable")
        mocked_has_smtp.assert_called_once_with(["mx.example.com"])

    @patch("email_validator.check_mail_domain")
    def test_validate_contacts_csv_collects_valid_and_invalid_rows(self, mocked_domain_check) -> None:
        mocked_domain_check.side_effect = [
            (True, None),
            (False, "no_mx_records"),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "emails.csv"
            csv_path.write_text(
                "company,email\nOpenAI,jobs@openai.com\nBroken,bad@example.com\n",
                encoding="utf-8",
            )

            summary = email_validator.validate_contacts_csv(csv_path)

        self.assertEqual(summary.total_checked, 2)
        self.assertEqual(summary.valid_count, 1)
        self.assertEqual(summary.invalid_count, 1)
        self.assertEqual(summary.invalid_contacts[0].line_number, 3)
        self.assertEqual(summary.invalid_contacts[0].result.reason, "no_mx_records")

    @patch("email_validator.check_mail_domain", return_value=(True, None))
    def test_load_invalid_domains_ignores_comments_and_blank_lines(self, mocked_domain_check) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_domains_path = Path(temp_dir) / "invalid_email_domains.txt"
            invalid_domains_path.write_text(
                "# invalid domains\n\nexample.com\nExample.org\n",
                encoding="utf-8",
            )

            loaded_domains = email_validator.load_invalid_domains(invalid_domains_path)

        self.assertEqual(loaded_domains, {"example.com", "example.org"})
        mocked_domain_check.assert_not_called()


class MainIntegrationTests(unittest.TestCase):
    def test_filter_invalid_contacts_returns_original_contacts_when_disabled(self) -> None:
        contacts = [{"email": "jobs@example.com", "company": "Example"}]

        with patch.object(config, "VALIDATE_EMAILS_BEFORE_SENDING", False):
            self.assertEqual(main.filter_invalid_contacts(contacts), contacts)

    @patch(
        "main.validate_email_address",
        side_effect=[
            email_validator.ValidationResult("jobs@example.com", True, None),
            email_validator.ValidationResult("bad@example.com", False, "no_mx_records"),
        ],
    )
    def test_filter_invalid_contacts_skips_invalid_rows(self, mocked_validate) -> None:
        contacts = [
            {"email": "jobs@example.com", "company": "Example"},
            {"email": "bad@example.com", "company": "Broken"},
        ]
        output = io.StringIO()

        with patch.object(config, "VALIDATE_EMAILS_BEFORE_SENDING", True):
            with redirect_stdout(output):
                filtered_contacts = main.filter_invalid_contacts(contacts)

        self.assertEqual(filtered_contacts, [{"email": "jobs@example.com", "company": "Example"}])
        self.assertEqual(mocked_validate.call_count, 2)
        self.assertIn("skipped: bad@example.com (email domain has no MX records)", output.getvalue())

    @patch(
        "main.validate_email_address",
        return_value=email_validator.ValidationResult(
            "jobs@example.com",
            False,
            "known_invalid_domain",
        ),
    )
    @patch("main.load_invalid_domains", return_value={"example.com"})
    def test_filter_invalid_contacts_uses_cached_invalid_domains(self, mocked_load_domains, mocked_validate) -> None:
        contacts = [{"email": "jobs@example.com", "company": "Example"}]
        output = io.StringIO()

        with patch.object(config, "VALIDATE_EMAILS_BEFORE_SENDING", True):
            with redirect_stdout(output):
                filtered_contacts = main.filter_invalid_contacts(contacts)

        self.assertEqual(filtered_contacts, [])
        mocked_load_domains.assert_called_once_with(main.INVALID_DOMAINS_FILE)
        mocked_validate.assert_called_once_with(
            "jobs@example.com",
            known_invalid_domains={"example.com"},
            invalid_domains_path=main.INVALID_DOMAINS_FILE,
        )
        self.assertIn("already known to be invalid", output.getvalue())


if __name__ == "__main__":
    unittest.main()
