import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from app.config import settings
from app.models import NotificationLog, utc_now

logger = logging.getLogger("codecoach.email")

# Jinja2 environment pointing to email templates directory
templates_dir = Path(__file__).resolve().parent.parent / "templates" / "email"
jinja_env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)

def render_email_template(template_name: str, context: Dict[str, Any]) -> str:
    template = jinja_env.get_template(template_name)
    merged_context = {
        "assistant_name": settings.ASSISTANT_NAME,
        "app_url": settings.APP_URL,
        **context
    }
    return template.render(**merged_context)

def send_html_email(
    db: Session,
    to_email: str,
    subject: str,
    template_name: str,
    context: Dict[str, Any],
    notification_type: str = "daily_reminder"
) -> bool:
    """
    Renders an HTML email template and sends it via smtplib (Gmail app password supported).
    Logs the result to notification_logs table.
    """
    recipient = to_email or settings.USER_EMAIL
    if not recipient or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP credentials or USER_EMAIL not configured in .env; email skipped.")
        return False

    html_content = render_email_template(template_name, {**context, "subject": subject})
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
    msg["To"] = recipient

    # HTML part
    part = MIMEText(html_content, "html")
    msg.attach(part)

    status = "failed"
    error_msg = None

    try:
        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15.0) as server:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(msg["From"], [recipient], msg.as_string())
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15.0) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(msg["From"], [recipient], msg.as_string())
        status = "sent"
        logger.info("Email '%s' sent successfully to %s", subject, recipient)
    except Exception as e:
        error_msg = str(e)
        logger.error("Failed to send email to %s: %s", recipient, e)

    log = NotificationLog(
        channel="email",
        notification_type=notification_type,
        subject=subject,
        content=f"Template: {template_name} to {recipient}",
        status=status,
        error_message=error_msg,
        sent_at=utc_now()
    )
    db.add(log)
    db.commit()

    return status == "sent"
