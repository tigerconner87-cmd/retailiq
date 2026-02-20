"""Real email sending service via SMTP (Gmail-compatible)."""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.config import settings

log = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST or "smtp.gmail.com"
        self.smtp_port = settings.SMTP_PORT or 587
        self.smtp_user = settings.SMTP_USER or ""
        self.smtp_password = settings.SMTP_PASSWORD or ""
        self.from_email = settings.ALERT_FROM_EMAIL or self.smtp_user

    @property
    def is_configured(self) -> bool:
        return bool(self.smtp_user and self.smtp_password)

    def send_email(self, to_email: str, subject: str, body_html: str, body_text: str = None) -> dict:
        """Send a real email via SMTP."""
        if not self.is_configured:
            return {"success": False, "error": "Email not configured. Add SMTP_USER and SMTP_PASSWORD to .env"}

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"Forge <{self.from_email}>"
            msg["To"] = to_email

            if body_text:
                msg.attach(MIMEText(body_text, "plain"))
            msg.attach(MIMEText(body_html, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            log.info("Email sent to %s: %s", to_email, subject)
            return {"success": True, "message": f"Email sent to {to_email}"}
        except Exception as e:
            log.exception("Failed to send email to %s", to_email)
            return {"success": False, "error": str(e)}

    def send_marketing_email(self, to_email: str, subject: str, body: str, shop_name: str) -> dict:
        """Send a branded marketing email with Forge template."""
        body_html_content = body.replace("\n", "<br>")
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f5f5f5;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px; border-radius: 12px 12px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">{shop_name}</h1>
            </div>
            <div style="padding: 24px; background: #ffffff; border-radius: 0 0 12px 12px;">
                {body_html_content}
            </div>
            <div style="text-align: center; padding: 16px; color: #999; font-size: 12px;">
                <p>Sent with love by {shop_name} | Powered by Forge</p>
                <p><a href="#" style="color: #999;">Unsubscribe</a></p>
            </div>
        </body>
        </html>
        """
        return self.send_email(to_email, subject, html, body)

    def send_test_email(self, to_email: str) -> dict:
        """Send a test email to verify SMTP configuration."""
        subject = "Forge Email Test"
        html = """
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 24px; border-radius: 12px; text-align: center; margin-bottom: 20px;">
                <h1 style="color: white; margin: 0;">Forge</h1>
            </div>
            <div style="padding: 24px; background: #f9f9f9; border-radius: 12px; text-align: center;">
                <h2 style="color: #333;">Your email integration is working!</h2>
                <p style="color: #666; font-size: 16px;">
                    Congratulations! Your Forge email integration is set up correctly.
                    Your AI agents can now send real emails to your customers.
                </p>
                <div style="margin: 24px 0; padding: 16px; background: #e8f5e9; border-radius: 8px; color: #2e7d32;">
                    Status: Connected
                </div>
            </div>
        </body>
        </html>
        """
        text = "Your Forge email integration is working! Your AI agents can now send real emails."
        return self.send_email(to_email, subject, html, text)


# Singleton instance
email_service = EmailService()
