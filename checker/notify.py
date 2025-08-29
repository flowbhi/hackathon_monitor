import os, smtplib, ssl, traceback
from email.mime.text import MIMEText
#from .state import update_last_notification
from .state_file import update_last_notification

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
MAIL_FROM = os.getenv("MAIL_FROM","monitor@demo.local")
MAIL_TO   = os.getenv("MAIL_TO","ops@example.com")

def _send(subject, body):
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        print("\n=== EMAIL (console fallback) ===")
        print(subject)
        print(body)
        print("=== END EMAIL ===\n")
        return
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO
    ctx = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls(context=ctx)
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(MAIL_FROM, [MAIL_TO], msg.as_string())

def notify_event(name, severity, event, details):
    subject = f"[{severity}][{event.upper()}] {name}"
    body = f"{name} -> {event}\n\nDetails:\n{details}"
    try:
        _send(subject, body)
        update_last_notification(name)
    except Exception:
        print("Email send failed:", traceback.format_exc())
