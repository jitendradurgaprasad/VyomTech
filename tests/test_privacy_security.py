"""
Security and privacy tests for FireWatch AI.
"""

from firewatch.notifications.providers import SmtpNotificationProvider
from firewatch.config import load_settings


def test_smtp_provider_masks_passwords():
    secret_pass = "super_secret_password_12345"
    provider = SmtpNotificationProvider(
        host="non-existent-smtp-domain-xyz-1234.invalid",
        port=587,
        username="alert_user",
        password=secret_pass,
        timeout=1
    )
    result = provider.send_notification("recipient@example.com", "Test", "Body", {})
    assert result.success is False
    assert secret_pass not in str(result.error)
    assert secret_pass not in str(result.provider_response)


def test_load_settings_does_not_hardcode_secrets():
    settings = load_settings()
    # Confirm default dummy or None
    assert settings.notifications.smtp_password is None or settings.notifications.smtp_password == "example_password_do_not_hardcode"
    assert settings.notifications.simulation_mode is True
