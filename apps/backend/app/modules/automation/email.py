"""Optional STARTTLS SMTP. No provider credentials or imported job data in messages."""

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings
from app.modules.automation.service import email_available


class EmailResult(Exception):
    def __init__(self, code, outcome):
        self.code, self.outcome = code, outcome


def send(notification, recipient):
    if not email_available():
        raise EmailResult("email_not_configured", "failed")
    message = EmailMessage()
    message["From"] = settings.smtp_sender
    message["To"] = recipient
    message["Subject"] = "Job Search Intelligence: workspace notification"
    message["Message-ID"] = f"<notification-{notification.id}@job-search-intelligence.local>"
    base = settings.app_base_url.rstrip("/")
    message.set_content(
        f"A notification is available in your private workspace.\n\n{base}/notifications\n\nManage or disable email notifications after signing in:\n{base}/notifications?preferences=1\n\nNo application was submitted and no employer was contacted."
    )
    connection = None
    try:
        connection = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        connection.ehlo()
        connection.starttls(context=ssl.create_default_context())
        connection.ehlo()
        if settings.smtp_username:
            connection.login(
                settings.smtp_username,
                settings.smtp_password.get_secret_value() if settings.smtp_password else "",
            )
    except smtplib.SMTPAuthenticationError:
        if connection:
            connection.close()
        raise EmailResult("email_auth_rejected", "failed") from None
    except smtplib.SMTPNotSupportedError:
        if connection:
            connection.close()
        raise EmailResult("email_tls_not_supported", "failed") from None
    except smtplib.SMTPResponseException as exc:
        if connection:
            connection.close()
        raise EmailResult(
            "email_handshake_rejected", "retry" if 400 <= exc.smtp_code < 500 else "failed"
        ) from None
    except (smtplib.SMTPException, OSError):
        if connection:
            connection.close()
        raise EmailResult("email_connection_unavailable", "retry") from None
    try:
        connection.send_message(message)
    except smtplib.SMTPRecipientsRefused:
        raise EmailResult("email_recipient_rejected", "failed") from None
    except smtplib.SMTPDataError as exc:
        raise EmailResult(
            "email_data_rejected", "retry" if 400 <= exc.smtp_code < 500 else "failed"
        ) from None
    except smtplib.SMTPSenderRefused as exc:
        raise EmailResult(
            "email_sender_rejected", "retry" if 400 <= exc.smtp_code < 500 else "failed"
        ) from None
    except (smtplib.SMTPException, OSError):
        # Acceptance may have occurred before the response was lost.
        raise EmailResult("email_acceptance_uncertain", "uncertain") from None
    finally:
        connection.close()
    return "accepted"
