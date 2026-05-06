# Email Outreach Script

This project is a small Python script for sending the same outreach email to a list of contacts with Gmail SMTP.

It does the following:

- reads contacts from `emails.csv`
- loads the message body from `template.txt`
- attaches `cv.pdf` to every email
- skips companies listed in `rejected.txt`
- waits a random delay between emails
- supports `DRY_RUN` mode for safe testing

## Files

- `main.py`: main logic
- `apply.py`: simple entrypoint
- `config.py`: SMTP settings, sender info, delays, and attachment name
- `emails.csv`: contact list
- `template.txt`: email body
- `rejected.txt`: companies to skip
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

- `DRY_RUN = True` sends nothing and only prints what would happen
- `CV_FILENAME = "cv.pdf"` sets the attached file
- `MIN_DELAY_SECONDS` and `MAX_DELAY_SECONDS` control the random wait time

## Run

From the `project/` folder:

```bash
python3 apply.py
```

For a real send, set `DRY_RUN = False` in `config.py`.
