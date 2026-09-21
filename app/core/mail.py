import logging
import os
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pydantic import EmailStr

logger = logging.getLogger(__name__)

# Load from ENV directly or use config.py
# Using os.environ for simplicity to avoid breaking config.py if missing
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
MAIL_FROM = os.getenv("MAIL_FROM", "noreply@tailor24.dev")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
MAIL_STARTTLS = os.getenv("MAIL_STARTTLS", "True").lower() in ("true", "1", "yes")
MAIL_SSL_TLS = os.getenv("MAIL_SSL_TLS", "False").lower() in ("true", "1", "yes")

_mail_configured = bool(MAIL_USERNAME and MAIL_PASSWORD)

if _mail_configured:
    conf = ConnectionConfig(
        MAIL_USERNAME=MAIL_USERNAME,
        MAIL_PASSWORD=MAIL_PASSWORD,
        MAIL_FROM=MAIL_FROM,
        MAIL_PORT=MAIL_PORT,
        MAIL_SERVER=MAIL_SERVER,
        MAIL_STARTTLS=MAIL_STARTTLS,
        MAIL_SSL_TLS=MAIL_SSL_TLS,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True
    )
    fm = FastMail(conf)
else:
    fm = None
    logger.warning("SMTP credentials not provided in .env. Emails will be mocked to the console.")

async def send_otp_email(email: str, otp: str):
    """Send an OTP email to the user. Mocks to console if SMTP is not configured."""
    subject = "TAILOR24 - Your Login OTP"
    body = f"""
    <html>
        <body>
            <h2>Welcome to TAILOR24</h2>
            <p>Your one-time password (OTP) is: <strong>{otp}</strong></p>
            <p>This code will expire in 5 minutes.</p>
        </body>
    </html>
    """
    
    if not _mail_configured:
        logger.info("\n" + "="*50)
        logger.info(f"MOCK EMAIL TO: {email}")
        logger.info(f"SUBJECT: {subject}")
        logger.info(f"OTP: {otp}")
        logger.info("="*50 + "\n")
        return

    message = MessageSchema(
        subject=subject,
        recipients=[email],
        body=body,
        subtype=MessageType.html
    )

    try:
        await fm.send_message(message)
        logger.info(f"OTP email sent to {email}")
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        raise
