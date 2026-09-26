"""
B11 — the local Outlook calendar adapter.

No test here touches a real Outlook install or pywin32's actual COM layer:
`OutlookCalendarAdapter` takes its dispatch function as a constructor argument
precisely so a fake COM double can stand in, exactly as `test_outlook_adapter.py`
does for B10's mail adapter. Nothing in this file is evidence the real
`win32com.client.Dispatch("Outlook.Application")` path works against a live
mailbox/calendar — only that the adapter's own logic (success, failure, and
the simulated/outlook selection) behaves correctly.
"""
import sys
import types
from datetime import datetime

from app.core import calendar_adapter
from app.core.calendar_adapter import (
    OutlookCalendarAdapter,
    SimulatedCalendarAdapter,
    get_calendar_adapter,
)


def test_simulated_adapter_reports_not_sent():
    result = SimulatedCalendarAdapter().send_invite(
        subject="Interview", start=datetime(2026, 9, 20, 10, 0),
        duration_minutes=45, location="Room 4",
        required_attendees=["panel@company.com", "candidate@example.com"],
        optional_attendees=[],
    )
    assert result.sent is False
    assert result.simulated is True
    assert "2 attendee" in result.detail


class _FakeRecipient:
    def __init__(self):
        self.Type = None


class _FakeRecipients:
    def __init__(self):
        self.added = []

    def Add(self, address):
        recipient = _FakeRecipient()
        recipient.address = address
        self.added.append(recipient)
        return recipient


class _FakeAppointmentItem:
    def __init__(self):
        self.MeetingStatus = None
        self.Subject = None
        self.Start = None
        self.Duration = None
        self.Location = None
        self.Body = None
        self.Recipients = _FakeRecipients()
        self.sent = False

    def Send(self):
        self.sent = True


class _FakeOutlookApplication:
    def __init__(self):
        self.created_items = []
        self.Session = type("Session", (), {"Accounts": [
            type("Account", (), {"SmtpAddress": "subhadeep.m@protivitiglobal.in"})(),
        ]})()

    def CreateItem(self, item_type):
        assert item_type == 1
        item = _FakeAppointmentItem()
        self.created_items.append(item)
        return item


def test_outlook_adapter_sends_through_the_fake_com_double(monkeypatch):
    monkeypatch.setattr(calendar_adapter.settings, "calendar_sender_email", "subhadeep.m@protivitiglobal.in")
    app = _FakeOutlookApplication()
    adapter = OutlookCalendarAdapter(dispatch=lambda: app)
    start = datetime(2026, 9, 20, 10, 0)

    result = adapter.send_invite(
        subject="Interview: Jane Doe", start=start, duration_minutes=45,
        location="Room 4", required_attendees=["panel@company.com", "candidate@example.com"],
        optional_attendees=["observer@company.com"], body="Round 1",
    )

    assert result.sent is True
    assert result.simulated is False
    assert "3 attendee" in result.detail
    assert len(app.created_items) == 1
    item = app.created_items[0]
    assert item.MeetingStatus == 1
    assert item.Subject == "Interview: Jane Doe"
    assert item.Start == start
    assert item.Duration == 45
    assert item.Location == "Room 4"
    assert item.Body == "Round 1"
    assert item.SendUsingAccount.SmtpAddress == "subhadeep.m@protivitiglobal.in"
    assert item.sent is True
    required = [r for r in item.Recipients.added if r.Type == 1]
    optional = [r for r in item.Recipients.added if r.Type == 2]
    assert {r.address for r in required} == {"panel@company.com", "candidate@example.com"}
    assert {r.address for r in optional} == {"observer@company.com"}


def test_outlook_adapter_never_raises_when_the_com_call_fails():
    def _broken_dispatch():
        raise RuntimeError("Outlook is not installed")

    adapter = OutlookCalendarAdapter(dispatch=_broken_dispatch)
    result = adapter.send_invite(
        subject="Interview", start=datetime(2026, 9, 20, 10, 0),
        duration_minutes=30, location="", required_attendees=["a@b.com"],
        optional_attendees=[],
    )

    assert result.sent is False
    assert result.simulated is False
    assert "Outlook calendar invite failed" in result.detail


def test_outlook_adapter_requires_configured_sender_account(monkeypatch):
    monkeypatch.setattr(calendar_adapter.settings, "calendar_sender_email", "subhadeep.m@protivitiglobal.in")
    app = _FakeOutlookApplication()
    app.Session = type("Session", (), {"Accounts": [
        type("Account", (), {"SmtpAddress": "other@example.com"})(),
    ]})()
    result = OutlookCalendarAdapter(dispatch=lambda: app).send_invite(
        subject="Interview", start=datetime(2026, 9, 20, 10),
        duration_minutes=45, location="Room 4",
        required_attendees=["chiranjib.sarma@protivitiglobal.in"], optional_attendees=[],
    )
    assert result.sent is False
    assert app.created_items[0].sent is False


def test_outlook_adapter_wraps_the_com_call_in_pythoncom_init_and_uninit(monkeypatch):
    """Same reasoning as the mail adapter (test_outlook_adapter.py): FastAPI
    runs a sync route handler in a worker thread, and COM requires each
    thread to initialize its own apartment."""
    calls = []
    fake_pythoncom = types.SimpleNamespace(
        CoInitialize=lambda: calls.append("init"),
        CoUninitialize=lambda: calls.append("uninit"),
    )
    monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)

    app = _FakeOutlookApplication()
    adapter = OutlookCalendarAdapter(dispatch=lambda: app)
    result = adapter.send_invite(
        subject="Interview", start=datetime(2026, 9, 20, 10, 0),
        duration_minutes=30, location="", required_attendees=["a@b.com"],
        optional_attendees=[],
    )

    assert result.sent is True
    assert calls == ["init", "uninit"]


def test_outlook_adapter_still_uninitializes_com_when_the_send_fails(monkeypatch):
    calls = []
    fake_pythoncom = types.SimpleNamespace(
        CoInitialize=lambda: calls.append("init"),
        CoUninitialize=lambda: calls.append("uninit"),
    )
    monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)

    def _broken_dispatch():
        raise RuntimeError("Outlook is not installed")

    adapter = OutlookCalendarAdapter(dispatch=_broken_dispatch)
    result = adapter.send_invite(
        subject="Interview", start=datetime(2026, 9, 20, 10, 0),
        duration_minutes=30, location="", required_attendees=["a@b.com"],
        optional_attendees=[],
    )

    assert result.sent is False
    assert calls == ["init", "uninit"]


def test_get_calendar_adapter_defaults_to_simulated(monkeypatch):
    monkeypatch.setattr(calendar_adapter.settings, "calendar_backend", "simulated")
    assert isinstance(get_calendar_adapter(), SimulatedCalendarAdapter)


def test_get_calendar_adapter_selects_outlook_when_configured(monkeypatch):
    monkeypatch.setattr(calendar_adapter.settings, "calendar_backend", "outlook")
    assert isinstance(get_calendar_adapter(), OutlookCalendarAdapter)


def test_get_calendar_adapter_falls_back_when_outlook_cannot_be_built(monkeypatch):
    monkeypatch.setattr(calendar_adapter.settings, "calendar_backend", "outlook")

    class _BrokenAdapter:
        def __init__(self):
            raise RuntimeError("pywin32 not installed")

    monkeypatch.setattr(calendar_adapter, "OutlookCalendarAdapter", _BrokenAdapter)
    assert isinstance(get_calendar_adapter(), SimulatedCalendarAdapter)
