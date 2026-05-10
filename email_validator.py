import argparse
import csv
import re
import smtplib
import sys
from dataclasses import dataclass
from pathlib import Path

import config

try:
    import dns.exception
    import dns.resolver
except ModuleNotFoundError:
    dns = None


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_EMAILS_FILE = BASE_DIR / "emails.csv"
EMAIL_COLUMN = "email"
EMAIL_PATTERN = re.compile(
    r"(?=.{1,254}$)(?=.{1,64}@)[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
VALIDATION_REASON_MESSAGES = {
    "empty_email": "email address is empty",
    "invalid_syntax": "email address has invalid syntax",
    "missing_domain": "email domain does not exist",
    "no_mx_records": "email domain has no MX records",
    "dns_error": "could not verify the email domain via DNS",
    "smtp_unreachable": "email domain has MX records but no responding SMTP server",
    "known_invalid_domain": "email domain is already known to be invalid",
    "validation_dependency_missing": "dnspython is not installed",
}
CACHEABLE_INVALID_DOMAIN_REASONS = {
    "missing_domain",
    "no_mx_records",
    "dns_error",
    "smtp_unreachable",
}
SMTP_CONNECT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class ValidationResult:
    normalized_email: str
    is_valid: bool
    reason: str | None = None


@dataclass(frozen=True)
class ContactValidationResult:
    line_number: int
    company: str
    result: ValidationResult


@dataclass(frozen=True)
class ValidationSummary:
    csv_path: Path
    total_checked: int
    valid_contacts: list[ContactValidationResult]
    invalid_contacts: list[ContactValidationResult]

    @property
    def valid_count(self) -> int:
        return len(self.valid_contacts)

    @property
    def invalid_count(self) -> int:
        return len(self.invalid_contacts)


def normalize_email_address(email_address: str) -> str:
    """Normalize email addresses so exact matching stays consistent."""
    return email_address.strip().lower()


def normalize_domain(domain: str) -> str:
    """Normalize domain names before caching or matching them."""
    return domain.strip().lower()


def extract_domain_from_email(email_address: str) -> str:
    """Extract the normalized domain from an email address."""
    normalized_email = normalize_email_address(email_address)
    _, _, domain = normalized_email.rpartition("@")
    return normalize_domain(domain)


def validation_dependency_error() -> str | None:
    """Return a readable error when the MX validation dependency is missing."""
    if dns is None:
        requirements_path = BASE_DIR / "requirements.txt"
        return (
            "dnspython is required for email validation. "
            f"Run: python3 -m pip install -r {requirements_path}"
        )

    return None


def format_validation_reason(reason: str | None) -> str:
    """Convert an internal validation reason into a readable message."""
    if reason is None:
        return "email address is valid"

    return VALIDATION_REASON_MESSAGES.get(reason, reason.replace("_", " "))


def load_invalid_domains(domains_path: Path) -> set[str]:
    """Load domains that should be skipped without validating them again."""
    if not domains_path.exists():
        return set()

    invalid_domains = set()

    with domains_path.open("r", encoding="utf-8") as domains_file:
        for line in domains_file:
            domain = normalize_domain(line)

            if not domain or domain.startswith("#"):
                continue

            invalid_domains.add(domain)

    return invalid_domains


def append_invalid_domains(domains_path: Path, domains: list[str], known_invalid_domains: set[str]) -> None:
    """Append newly discovered invalid domains to the cache file."""
    new_domains = []

    for domain in domains:
        normalized_domain = normalize_domain(domain)

        if not normalized_domain or normalized_domain in known_invalid_domains:
            continue

        known_invalid_domains.add(normalized_domain)
        new_domains.append(normalized_domain)

    if not new_domains:
        return

    with domains_path.open("a", encoding="utf-8") as domains_file:
        for domain in new_domains:
            domains_file.write(f"{domain}\n")


def remember_invalid_domain(
    domain: str,
    reason: str | None,
    invalid_domains_path: Path | None,
    known_invalid_domains: set[str] | None,
) -> None:
    """Persist permanently invalid domains so future runs can skip them early."""
    if reason not in CACHEABLE_INVALID_DOMAIN_REASONS or invalid_domains_path is None:
        return

    cached_domains = known_invalid_domains if known_invalid_domains is not None else load_invalid_domains(invalid_domains_path)
    append_invalid_domains(invalid_domains_path, [domain], cached_domains)


def extract_mx_hosts(mx_answers) -> list[str]:
    """Normalize MX answers into an ordered list of SMTP hosts."""
    ordered_answers = sorted(mx_answers, key=lambda answer: getattr(answer, "preference", 0))
    return [
        normalize_domain(str(answer.exchange).rstrip("."))
        for answer in ordered_answers
        if str(answer.exchange).strip()
    ]


def has_responding_smtp_server(mx_hosts: list[str]) -> bool:
    """Return True when at least one MX host accepts an SMTP connection."""
    for mx_host in mx_hosts:
        try:
            with smtplib.SMTP(mx_host, timeout=SMTP_CONNECT_TIMEOUT_SECONDS) as smtp:
                smtp.noop()
            return True
        except Exception:
            continue

    return False


def check_mail_domain(domain: str) -> tuple[bool, str | None]:
    """Verify that the domain exists and publishes MX records."""
    if validation_dependency_error() is not None:
        return False, "validation_dependency_missing"

    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 5

    try:
        answers = resolver.resolve(domain, "MX")
    except dns.resolver.NXDOMAIN:
        return False, "missing_domain"
    except dns.resolver.NoAnswer:
        return False, "no_mx_records"
    except dns.exception.DNSException:
        return False, "dns_error"

    if not answers:
        return False, "no_mx_records"

    mx_hosts = extract_mx_hosts(answers)

    if not mx_hosts:
        return False, "no_mx_records"

    if config.SMTP_PROBE_ENABLED and not has_responding_smtp_server(mx_hosts):
        return False, "smtp_unreachable"

    return True, None


def validate_email_address(
    email_address: str,
    *,
    known_invalid_domains: set[str] | None = None,
    invalid_domains_path: Path | None = None,
) -> ValidationResult:
    """Validate email syntax and verify that the domain has MX records."""
    normalized_email = normalize_email_address(email_address)

    if not normalized_email:
        return ValidationResult(normalized_email, False, "empty_email")

    if not EMAIL_PATTERN.fullmatch(normalized_email):
        return ValidationResult(normalized_email, False, "invalid_syntax")

    domain = extract_domain_from_email(normalized_email)

    if known_invalid_domains is not None and domain in known_invalid_domains:
        return ValidationResult(normalized_email, False, "known_invalid_domain")

    has_valid_domain, reason = check_mail_domain(domain)

    if not has_valid_domain:
        remember_invalid_domain(domain, reason, invalid_domains_path, known_invalid_domains)
        return ValidationResult(normalized_email, False, reason)

    return ValidationResult(normalized_email, True)


def validate_contacts_csv(csv_path: Path, *, invalid_domains_path: Path | None = None) -> ValidationSummary:
    """Validate every row in a contacts CSV."""
    valid_contacts: list[ContactValidationResult] = []
    invalid_contacts: list[ContactValidationResult] = []
    known_invalid_domains = (
        load_invalid_domains(invalid_domains_path) if invalid_domains_path is not None else None
    )

    with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        if EMAIL_COLUMN not in (reader.fieldnames or []):
            raise ValueError("emails.csv must contain a column named 'email'.")

        for line_number, row in enumerate(reader, start=2):
            email_address = row.get(EMAIL_COLUMN) or ""
            company_name = (row.get("company") or "").strip()
            result = validate_email_address(
                email_address,
                known_invalid_domains=known_invalid_domains,
                invalid_domains_path=invalid_domains_path,
            )
            contact_result = ContactValidationResult(line_number, company_name, result)

            if result.is_valid:
                valid_contacts.append(contact_result)
            else:
                invalid_contacts.append(contact_result)

    return ValidationSummary(
        csv_path=csv_path,
        total_checked=len(valid_contacts) + len(invalid_contacts),
        valid_contacts=valid_contacts,
        invalid_contacts=invalid_contacts,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for standalone CSV validation."""
    parser = argparse.ArgumentParser(description="Validate email addresses in a contacts CSV.")
    parser.add_argument(
        "csv_path",
        nargs="?",
        default=str(DEFAULT_EMAILS_FILE),
        help="Path to the contacts CSV file. Defaults to project/emails.csv.",
    )
    return parser.parse_args(argv)


def run_cli(argv: list[str] | None = None) -> int:
    """Run standalone CSV validation and return a process exit code."""
    dependency_error = validation_dependency_error()

    if dependency_error is not None:
        print(f"failed: {dependency_error}")
        return 2

    args = parse_args(argv)
    csv_path = Path(args.csv_path).expanduser().resolve()
    invalid_domains_path = BASE_DIR / config.INVALID_DOMAINS_FILENAME

    try:
        summary = validate_contacts_csv(
            csv_path,
            invalid_domains_path=invalid_domains_path,
        )
    except Exception as error:
        print(f"failed: could not validate {csv_path} -> {error}")
        return 2

    for invalid_contact in summary.invalid_contacts:
        company_label = f" ({invalid_contact.company})" if invalid_contact.company else ""
        print(
            f"invalidated line {invalid_contact.line_number}: "
            f"{invalid_contact.result.normalized_email or '<empty>'}{company_label} "
            f"-> {format_validation_reason(invalid_contact.result.reason)}"
        )

    print(
        f"checked {summary.total_checked} row(s) in {csv_path.name}: "
        f"{summary.valid_count} valid, {summary.invalid_count} invalid"
    )
    return 0 if summary.invalid_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:]))
