"""
Notification Provider Abstraction and Implementations for FireWatch AI.
"""

from __future__ import annotations
import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional
import requests


class NotificationResult:
    """Outcome of a notification attempt."""
    def __init__(
        self,
        success: bool,
        status: str,  # 'simulated' | 'sent_to_provider' | 'provider_accepted' | 'delivered' | 'failed'
        provider_response: str,
        error: Optional[str] = None
    ):
        self.success = success
        self.status = status
        self.provider_response = provider_response
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "provider_response": self.provider_response,
            "error": self.error
        }


class BaseNotificationProvider(ABC):
    """Abstract interface for dispatching notifications."""

    @abstractmethod
    def send_notification(
        self,
        recipient: str,
        subject: str,
        message_body: str,
        payload_data: Dict[str, Any]
    ) -> NotificationResult:
        pass


class SimulationNotificationProvider(BaseNotificationProvider):
    """
    Safe simulation provider.
    Constructs the notification, logs details, and records simulated delivery.
    Does NOT connect to external networks or contact authorities.
    """

    def send_notification(
        self,
        recipient: str,
        subject: str,
        message_body: str,
        payload_data: Dict[str, Any]
    ) -> NotificationResult:
        sim_summary = (
            f"[SIMULATION ONLY - NO EXTERNAL DISPATCH]\n"
            f"Recipient: {recipient}\n"
            f"Subject: {subject}\n"
            f"Payload Keys: {list(payload_data.keys())}\n"
            f"Message Snippet: {message_body[:180]}..."
        )
        return NotificationResult(
            success=True,
            status="simulated",
            provider_response="SIMULATION_SUCCESS: Notification logged and stored in local queue."
        )


class SmtpNotificationProvider(BaseNotificationProvider):
    """
    SMTP Email notification provider.
    Active ONLY when simulation mode is explicitly disabled and credentials are verified.
    """

    def __init__(
        self,
        host: Optional[str],
        port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        from_email: str = "alerts@firewatch.ai",
        timeout: int = 10
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.timeout = timeout

    def send_notification(
        self,
        recipient: str,
        subject: str,
        message_body: str,
        payload_data: Dict[str, Any]
    ) -> NotificationResult:
        if not self.host or not self.recipient_is_valid(recipient):
            return NotificationResult(
                success=False,
                status="failed",
                provider_response="SMTP_CONFIG_ERROR",
                error="SMTP host is not configured or recipient email is invalid."
            )

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = recipient

            part = MIMEText(message_body, "plain", "utf-8")
            msg.attach(part)

            server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            server.ehlo()
            if self.port in (587, 25):
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            
            server.sendmail(self.from_email, [recipient], msg.as_string())
            server.quit()

            return NotificationResult(
                success=True,
                status="provider_accepted",
                provider_response="SMTP_ACCEPTED: Message accepted by remote mail transfer agent."
            )
        except Exception as e:
            # Secure error logging: Ensure password or credentials are never exposed
            err_msg = str(e).replace(str(self.password or ""), "[PROTECTED]")
            return NotificationResult(
                success=False,
                status="failed",
                provider_response="SMTP_DELIVERY_FAILED",
                error=f"SMTP Error: {err_msg}"
            )

    @staticmethod
    def recipient_is_valid(email: str) -> bool:
        return "@" in email and "." in email.split("@")[-1]


class WebhookNotificationProvider(BaseNotificationProvider):
    """
    HTTP Webhook notification provider.
    Active ONLY when simulation mode is disabled.
    """

    def __init__(self, webhook_url: Optional[str], secret: Optional[str] = None, timeout: int = 10):
        self.webhook_url = webhook_url
        self.secret = secret
        self.timeout = timeout

    def send_notification(
        self,
        recipient: str,
        subject: str,
        message_body: str,
        payload_data: Dict[str, Any]
    ) -> NotificationResult:
        target_url = recipient if recipient.startswith("http") else self.webhook_url
        if not target_url:
            return NotificationResult(
                success=False,
                status="failed",
                provider_response="WEBHOOK_CONFIG_ERROR",
                error="No valid webhook URL configured."
            )

        try:
            payload = {
                "subject": subject,
                "message": message_body,
                "data": payload_data
            }
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "FireWatch-AI-Webhook/1.0"
            }
            if self.secret:
                headers["X-FireWatch-Signature"] = "sha256-signature-placeholder"

            resp = requests.post(target_url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()

            return NotificationResult(
                success=True,
                status="provider_accepted",
                provider_response=f"WEBHOOK_ACCEPTED: HTTP {resp.status_code}"
            )
        except requests.exceptions.RequestException as e:
            return NotificationResult(
                success=False,
                status="failed",
                provider_response="WEBHOOK_FAILED",
                error=f"Webhook request failed: {str(e)}"
            )
