# Email Outreach Script

This project is a small Python script for sending the same outreach email to a list of contacts with Gmail SMTP.

It does the following:

- reads contacts from `emails.csv`
- validates email syntax, MX records, and optionally SMTP server response before sending
- loads the message body from `template.txt`
- attaches `cv.pdf` to every email
- skips companies listed in `rejected.txt`
- can optionally skip exact email addresses already listed in `sent.txt`
- waits a random delay between emails
- can optionally send batches with hidden BCC recipients
- supports `DRY_RUN` mode for safe testing

## Files

- `main.py`: main logic
- `apply.py`: simple entrypoint
- `email_validator.py`: standalone email validation, MX checks, and optional SMTP reachability checks
- `config.py`: SMTP settings, sender info, delays, attachment name, sent-file checks, and BCC batching
- `emails.csv`: contact list
- `invalid_email_domains.txt`: cached domains that failed domain-level validation so they can be skipped next time
- `template.txt`: email body
- `rejected.txt`: companies to skip
- `sent.txt`: exact email addresses that were already sent
- `cv.pdf`: CV attached to each email

## Contact Format

Preferred CSV format:

```csv
company,email
OpenAI,jobs@openai.com
Anthropic,hr@anthropic.com
```

If the `company` column is missing, the script tries to derive the company name from the email domain.

## Configuration

You can configure the sender information in `.env`:

```env
SENDER_EMAIL=your_email@gmail.com
SENDER_NAME=Ayoub DIOURI
GMAIL_APP_PASSWORD=your_app_password
EMAIL_SUBJECT=Your subject here
```

Important settings in `config.py`:

- `VALIDATE_EMAILS_BEFORE_SENDING = True` validates recipient syntax, MX records, and SMTP
  reachability before sending and requires DNS/network access
- `SMTP_PROBE_ENABLED = True` controls the extra SMTP connect probe after MX lookup
- `INVALID_DOMAINS_FILENAME = "invalid_email_domains.txt"` stores domains that were already
  confirmed invalid so they are skipped on later runs
- `DRY_RUN = True` sends nothing and only prints what would happen
- `CV_FILENAME = "cv.pdf"` sets the attached file
- `SENT_FILENAME = "sent.txt"` points to the local file tracking already-sent email addresses
- `SKIP_EMAILS_ALREADY_IN_SENT = True` skips any exact email already present in `sent.txt`
- `BATCH_SEND_BY_BCC = True` switches from one-by-one sends to hidden BCC batches
- `BCC_BATCH_SIZE = 10` controls how many contacts are included in each BCC batch
- `MIN_DELAY_SECONDS` and `MAX_DELAY_SECONDS` control the random wait time

## Run

From the `project/` folder:

```bash
python3 -m pip install -r requirements.txt
python3 apply.py
```

For a real send, set `DRY_RUN = False` in `config.py`.

If you want to hide recipients from each other while still sending in groups, also set `BATCH_SEND_BY_BCC = True`.

Every successful real send is appended to `sent.txt`, even if `SKIP_EMAILS_ALREADY_IN_SENT` is disabled.

## Validate Contacts Only

To run the validator by itself without sending email:

```bash
python3 email_validator.py
```

MX validation depends on live DNS lookups, and the optional SMTP probe needs working
network access.

When a domain is confirmed missing or has no MX records, it is appended to
`invalid_email_domains.txt`. Future runs skip any address from those domains without
checking them again. The file is auto-generated and ignored by git.

When the optional SMTP probe is enabled, domains that have MX records but no responding
SMTP server are also added to the same cache file.

You can also point it at a different CSV file:

```bash
python3 email_validator.py /path/to/contacts.csv
```
