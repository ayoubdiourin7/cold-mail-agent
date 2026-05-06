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

# File attached to every email.
CV_FILENAME = "cv.pdf"

# If True, no real email is sent.
DRY_RUN = False

# Random wait time between emails, in seconds.
MIN_DELAY_SECONDS = 20
MAX_DELAY_SECONDS = 40
