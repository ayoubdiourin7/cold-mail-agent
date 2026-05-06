import csv
import random
import re
import smtplib
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

import config


# Keep file paths relative to this script so the project works from any folder.
BASE_DIR = Path(__file__).resolve().parent
EMAILS_FILE = BASE_DIR / "emails.csv"
REJECTED_FILE = BASE_DIR / "rejected.txt"
TEMPLATE_FILE = BASE_DIR / "template.txt"
CV_FILE = BASE_DIR / config.CV_FILENAME
BCC_TO_HEADER = "undisclosed-recipients:;"


def extract_company_name_from_email(email_address: str) -> str:
    """Build a simple company name from the email domain when none is provided."""
    domain = email_address.split("@")[-1].strip().lower()
    domain_parts = [part for part in domain.split(".") if part]

    if not domain_parts:
        return email_address

    if len(domain_parts) >= 3 and domain_parts[-2] in {"co", "com", "org", "net", "gov", "ac"}:
        return domain_parts[-3]

    if len(domain_parts) >= 2:
        return domain_parts[-2]

    return domain_parts[0]


def normalize_company_name(company_name: str) -> str:
    """Normalize company names so manual entries are easy to match."""
    cleaned_name = company_name.strip().lower()

    if "@" in cleaned_name:
        cleaned_name = extract_company_name_from_email(cleaned_name)

    return re.sub(r"[^a-z0-9]+", "", cleaned_name)


def load_emails(csv_path: Path) -> list[dict[str, str]]:
    """Load emails from CSV and attach a company name to each row."""
    contacts = []
    seen = set()

    with csv_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        if "email" not in (reader.fieldnames or []):
            raise ValueError("emails.csv must contain a column named 'email'.")

        for row in reader:
            email_address = (row.get("email") or "").strip().lower()
            company_name = (row.get("company") or "").strip()

            if not email_address:
                continue

            if email_address in seen:
                continue

            if not company_name:
                company_name = extract_company_name_from_email(email_address)

            seen.add(email_address)
            contacts.append(
                {
                    "email": email_address,
                    "company": company_name,
                }
            )

    return contacts


def load_rejected_companies(rejected_path: Path) -> set[str]:
    """Read rejected company names from rejected.txt."""
    if not rejected_path.exists():
        return set()

    rejected_companies = set()

    with rejected_path.open("r", encoding="utf-8") as rejected_file:
        for line in rejected_file:
            company_name = line.strip()

            if not company_name or company_name.startswith("#"):
                continue

            normalized_name = normalize_company_name(company_name)

            if normalized_name:
                rejected_companies.add(normalized_name)

    return rejected_companies


def load_template(template_path: Path) -> str:
    """Load the email body from template.txt."""
    return template_path.read_text(encoding="utf-8")


def build_message(to_header: str, body: str) -> MIMEMultipart:
    """Build the email message with the text body and CV attachment."""
    message = MIMEMultipart()
    message["Subject"] = config.EMAIL_SUBJECT
    message["From"] = formataddr((config.SENDER_NAME, config.SENDER_EMAIL))
    message["To"] = to_header

    message.attach(MIMEText(body, "plain", "utf-8"))

    with CV_FILE.open("rb") as cv_file:
        attachment = MIMEApplication(cv_file.read(), _subtype="pdf")

    attachment.add_header(
        "Content-Disposition",
        "attachment",
        filename=CV_FILE.name,
    )
    message.attach(attachment)
    return message


def send_email(recipients: list[str], body: str, *, to_header: str) -> None:
    """Send one email using Gmail SMTP, or print the action in dry-run mode."""
    if config.DRY_RUN:
        if len(recipients) == 1 and to_header == recipients[0]:
            print(
                f"dry run: would send '{config.EMAIL_SUBJECT}' "
                f"from {config.SENDER_NAME} <{config.SENDER_EMAIL}> to {recipients[0]} "
                f"with attachment {CV_FILE.name}"
            )
        else:
            print(
                f"dry run: would send '{config.EMAIL_SUBJECT}' "
                f"from {config.SENDER_NAME} <{config.SENDER_EMAIL}> "
                f"with To header '{to_header}' and hidden BCC recipients "
                f"{', '.join(recipients)} with attachment {CV_FILE.name}"
            )
        return

    message = build_message(to_header, body)

    with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SENDER_EMAIL, config.SENDER_PASSWORD)
        server.sendmail(config.SENDER_EMAIL, recipients, message.as_string())


def wait_before_next_email() -> None:
    """Wait a random number of seconds between sends."""
    delay_seconds = random.randint(
        config.MIN_DELAY_SECONDS,
        config.MAX_DELAY_SECONDS,
    )

    if config.DRY_RUN:
        print(f"dry run: would wait {delay_seconds} seconds before the next send")
        return

    print(f"waiting {delay_seconds} seconds before the next send...")
    time.sleep(delay_seconds)


def validate_config() -> bool:
    """Check the required configuration before sending anything."""
    errors = []

    if not config.SENDER_EMAIL.strip():
        errors.append("SENDER_EMAIL is empty in config.py.")

    if not config.EMAIL_SUBJECT.strip():
        errors.append("EMAIL_SUBJECT is empty in config.py.")

    if not config.DRY_RUN and not config.SENDER_PASSWORD.strip():
        errors.append(
            "GMAIL_APP_PASSWORD is missing. Set it in your environment before running."
        )

    if not CV_FILE.exists():
        errors.append(f"CV file not found: {CV_FILE.name}")

    if config.MIN_DELAY_SECONDS < 0:
        errors.append("MIN_DELAY_SECONDS cannot be negative.")

    if config.MAX_DELAY_SECONDS < config.MIN_DELAY_SECONDS:
        errors.append("MAX_DELAY_SECONDS must be greater than or equal to MIN_DELAY_SECONDS.")

    if config.BATCH_SEND_BY_BCC and config.BCC_BATCH_SIZE < 1:
        errors.append("BCC_BATCH_SIZE must be greater than or equal to 1.")

    if errors:
        for error in errors:
            print(f"failed: {error}")
        return False

    return True


def build_send_batches(contacts: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    """Split eligible contacts into one-by-one sends or BCC batches."""
    if not config.BATCH_SEND_BY_BCC:
        return [[contact] for contact in contacts]

    return [
        contacts[index : index + config.BCC_BATCH_SIZE]
        for index in range(0, len(contacts), config.BCC_BATCH_SIZE)
    ]


def main() -> None:
    """Run the email outreach workflow from start to finish."""
    if not validate_config():
        return

    try:
        contacts = load_emails(EMAILS_FILE)
        rejected_companies = load_rejected_companies(REJECTED_FILE)
        email_body = load_template(TEMPLATE_FILE)
    except Exception as error:
        print(f"failed: could not load project files -> {error}")
        return

    if not contacts:
        print("failed: no email addresses found in emails.csv")
        return

    eligible_contacts = []

    for contact in contacts:
        email_address = contact["email"]
        company_name = contact["company"]
        normalized_company_name = normalize_company_name(company_name)

        if normalized_company_name in rejected_companies:
            print(f"skipped: {email_address} ({company_name} is in rejected.txt)")
            continue

        eligible_contacts.append(contact)

    if not eligible_contacts:
        print("failed: no email addresses left after applying rejected.txt")
        return

    send_batches = build_send_batches(eligible_contacts)

    for index, batch in enumerate(send_batches):
        batch_recipients = [contact["email"] for contact in batch]

        if config.BATCH_SEND_BY_BCC:
            print(
                f"sending batch via BCC to {len(batch_recipients)} recipients: "
                f"{', '.join(batch_recipients)}"
            )
        else:
            print(f"sending to {batch_recipients[0]} ({batch[0]['company']})...")

        try:
            send_email(
                batch_recipients,
                email_body,
                to_header=BCC_TO_HEADER if config.BATCH_SEND_BY_BCC else batch_recipients[0],
            )
            if config.BATCH_SEND_BY_BCC:
                print(
                    f"success: sent BCC batch to {len(batch_recipients)} recipients"
                )
            else:
                print(f"success: {batch_recipients[0]}")
        except Exception as error:
            if config.BATCH_SEND_BY_BCC:
                print(f"failed: BCC batch {', '.join(batch_recipients)} -> {error}")
            else:
                print(f"failed: {batch_recipients[0]} -> {error}")
            continue

        if index < len(send_batches) - 1:
            wait_before_next_email()


if __name__ == "__main__":
    main()
