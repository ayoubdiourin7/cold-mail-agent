import os
from pathlib import Path


def load_local_env_file() -> None:
    """Load simple KEY=VALUE pairs from a local .env file if it exists."""
    env_path = Path(__file__).resolve().parent / ".env"

    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped_line = line.strip()

        if not stripped_line or stripped_line.startswith("#") or "=" not in stripped_line:
            continue

        key, value = stripped_line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_local_env_file()

# Gmail SMTP settings.
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# The Gmail address you want to send from.
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")

# The sender name shown to recipients.
SENDER_NAME = os.getenv("SENDER_NAME", "")

# Use a Gmail App Password instead of hardcoding a real password.
# Example:
# export GMAIL_APP_PASSWORD="your-16-character-app-password"

SENDER_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# Subject line used for every outreach email.
EMAIL_SUBJECT = os.getenv("EMAIL_SUBJECT", "")

# Main body text of the email.
MAIL_TO_SEND = "templaceRelance.txt"

# File attached to every email.
CV_FILENAME = "cv_ayoub_sof.pdf"

# Local file storing recipients that were already sent an email.
SENT_FILENAME = "sent.txt"

# Local file caching domains that failed validation permanently.
INVALID_DOMAINS_FILENAME = "invalid_email_domains.txt"

# If True, validate recipient email syntax and MX records before sending.
# This requires dnspython and DNS/network access.
VALIDATE_EMAILS_BEFORE_SENDING = True

# If True, also try opening an SMTP connection to the MX host before accepting the address.
SMTP_PROBE_ENABLED = True

# If True, no real email is sent.
DRY_RUN = True

# If True, skip recipients already present in SENT_FILENAME before sending.
SKIP_EMAILS_ALREADY_IN_SENT = False

# If True, send contacts in hidden BCC batches instead of one by one.
BATCH_SEND_BY_BCC = False

# Number of contacts per hidden BCC batch when BATCH_SEND_BY_BCC is enabled.
BCC_BATCH_SIZE = 10

# Random wait time between emails, in seconds.
MIN_DELAY_SECONDS = 2
MAX_DELAY_SECONDS = 4
