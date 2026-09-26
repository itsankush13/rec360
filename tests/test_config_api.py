"""Send-mode disclosure endpoint (truthfulness fix, demo 2026-09-14).

The frontend badges that used to hardcode "SIMULATED" now ask this endpoint
which backend is really active, so the badge never lies once Outlook goes
live. See app/api/config.py.
"""


def test_send_modes_reports_configured_backends(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "email_backend", "outlook")
    monkeypatch.setattr(settings, "calendar_backend", "simulated")

    resp = client.get("/api/config/send-modes")

    assert resp.status_code == 200
    assert resp.json() == {"email_backend": "outlook", "calendar_backend": "simulated"}


def test_send_modes_exposes_nothing_else(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "azure_openai_api_key", "super-secret-key")
    monkeypatch.setattr(settings, "email_sender_address", "real-mailbox@example.com")

    resp = client.get("/api/config/send-modes")

    body = resp.json()
    assert set(body.keys()) == {"email_backend", "calendar_backend"}
    assert "super-secret-key" not in resp.text
    assert "real-mailbox@example.com" not in resp.text
