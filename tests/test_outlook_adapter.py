"""
B10 — the local Outlook mail adapter.

No test here touches a real Outlook install or pywin32's actual COM layer:
`OutlookMailAdapter` takes its dispatch function as a constructor argument
precisely so a fake COM double can stand in. Nothing in this file is
evidence the real `win32com.client.Dispatch("Outlook.Application")` path
works against a live mailbox — only that the adapter's own logic (success,
failure, and the simulated/outlook selection) behaves correctly.

The `pythoncom` module itself is real here (pywin32 is installed in this
environment) — `CoInitialize`/`CoUninitialize` genuinely run. Only the
`win32com.client.Dispatch("Outlook.Application")` call is faked, via the
`dispatch=` constructor argument, exactly like the rest of this file.
"""
import os
import sys
import types

from app.core import outlook_adapter
from app.core.outlook_adapter import (
    OutlookMailAdapter,
    SimulatedMailAdapter,
    get_mail_adapter,
)


def test_simulated_adapter_reports_not_sent():
    result = SimulatedMailAdapter().send(
        to_address="a@b.com", subject="Hi", body="Hello there",
    )
    assert result.sent is False
    assert result.simulated is True
    assert "a@b.com" in result.detail


def test_simulated_adapter_mentions_the_attachment_filename():
    result = SimulatedMailAdapter().send(
        to_address="a@b.com", subject="Hi", body="Hello there",
        attachments=[("shortlist.zip", b"zip-bytes")],
    )
    assert result.simulated is True
    assert "shortlist.zip" in result.detail


class _FakeAttachments:
    def __init__(self):
        self.added = []

    def Add(self, path):
        self.added.append(path)


class _FakeMailItem:
    def __init__(self):
        self.To = None
        self.CC = None
        self.Subject = None
        self.Body = None
        self.HTMLBody = None
        self.SendUsingAccount = None
        self.Attachments = _FakeAttachments()
        self.sent = False

    def Send(self):
        self.sent = True


class _FakeOutlookApplication:
    def __init__(self, accounts=None):
        self.created_items = []
        self.Session = type("Session", (), {
            "Accounts": accounts if accounts is not None else [],
        })()

    def CreateItem(self, item_type):
        assert item_type == 0
        item = _FakeMailItem()
        self.created_items.append(item)
        return item


def test_outlook_adapter_sends_through_the_fake_com_double():
    app = _FakeOutlookApplication()
    adapter = OutlookMailAdapter(dispatch=lambda: app)

    result = adapter.send(to_address="candidate@example.com", subject="Subj", body="Body text")

    assert result.sent is True
    assert result.simulated is False
    assert "candidate@example.com" in result.detail
    assert len(app.created_items) == 1
    item = app.created_items[0]
    assert item.To == "candidate@example.com"
    assert item.Subject == "Subj"
    assert item.Body == "Body text"
    assert item.sent is True


def test_outlook_adapter_never_raises_when_the_com_call_fails():
    def _broken_dispatch():
        raise RuntimeError("Outlook is not installed")

    adapter = OutlookMailAdapter(dispatch=_broken_dispatch)
    result = adapter.send(to_address="a@b.com", subject="Subj", body="Body")

    assert result.sent is False
    assert result.simulated is False
    assert "Outlook send failed" in result.detail


def test_outlook_adapter_sets_cc_when_given():
    app = _FakeOutlookApplication()
    adapter = OutlookMailAdapter(dispatch=lambda: app)

    result = adapter.send(
        to_address="candidate@example.com", subject="Subj", body="Body text",
        cc_address="recruiter@example.com",
    )

    assert result.sent is True
    item = app.created_items[0]
    assert item.CC == "recruiter@example.com"


def test_outlook_adapter_leaves_cc_unset_when_not_given():
    app = _FakeOutlookApplication()
    adapter = OutlookMailAdapter(dispatch=lambda: app)

    adapter.send(to_address="candidate@example.com", subject="Subj", body="Body text")

    assert app.created_items[0].CC is None


def test_outlook_adapter_sets_html_body_when_given():
    app = _FakeOutlookApplication()
    adapter = OutlookMailAdapter(dispatch=lambda: app)

    adapter.send(
        to_address="candidate@example.com", subject="Subj", body="Plain text",
        html_body="<p>Rich text</p>",
    )

    item = app.created_items[0]
    assert item.Body == "Plain text"
    assert item.HTMLBody == "<p>Rich text</p>"


def test_outlook_adapter_leaves_html_body_unset_when_not_given():
    app = _FakeOutlookApplication()
    adapter = OutlookMailAdapter(dispatch=lambda: app)

    adapter.send(to_address="candidate@example.com", subject="Subj", body="Plain text")

    assert app.created_items[0].HTMLBody is None


def test_outlook_adapter_sends_from_the_configured_account(monkeypatch):
    """
    B10: mirrors B11's `calendar_sender_email` — the account a real send goes
    out from should be explicit, not whatever Outlook's own default happens
    to be on the machine.
    """
    monkeypatch.setattr(outlook_adapter.settings, "email_sender_address",
                         "daipayan.r@protivitiglobal.in")
    account = type("Account", (), {"SmtpAddress": "daipayan.r@protivitiglobal.in"})()
    app = _FakeOutlookApplication(accounts=[account])
    adapter = OutlookMailAdapter(dispatch=lambda: app)

    result = adapter.send(to_address="candidate@example.com", subject="Subj", body="Body")

    assert result.sent is True
    assert app.created_items[0].SendUsingAccount is account


def test_outlook_adapter_requires_the_configured_account_to_be_signed_in(monkeypatch):
    """
    A configured account that is not signed in must fail honestly — not
    silently fall back to whatever Outlook's default account is, which
    would defeat the point of configuring one at all.
    """
    monkeypatch.setattr(outlook_adapter.settings, "email_sender_address",
                         "daipayan.r@protivitiglobal.in")
    other_account = type("Account", (), {"SmtpAddress": "someone.else@example.com"})()
    app = _FakeOutlookApplication(accounts=[other_account])
    adapter = OutlookMailAdapter(dispatch=lambda: app)

    result = adapter.send(to_address="candidate@example.com", subject="Subj", body="Body")

    assert result.sent is False
    assert result.simulated is False
    assert app.created_items[0].sent is False


def test_outlook_adapter_wraps_the_com_call_in_pythoncom_init_and_uninit(monkeypatch):
    """
    FastAPI runs a sync route handler in a worker thread; COM requires each
    thread to initialize its own apartment. `pythoncom` is swapped out via
    sys.modules so this checks the adapter's own call sequence rather than
    the real COM subsystem.
    """
    calls = []
    fake_pythoncom = types.SimpleNamespace(
        CoInitialize=lambda: calls.append("init"),
        CoUninitialize=lambda: calls.append("uninit"),
    )
    monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)

    app = _FakeOutlookApplication()
    adapter = OutlookMailAdapter(dispatch=lambda: app)
    result = adapter.send(to_address="a@b.com", subject="Subj", body="Body")

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

    adapter = OutlookMailAdapter(dispatch=_broken_dispatch)
    result = adapter.send(to_address="a@b.com", subject="Subj", body="Body")

    assert result.sent is False
    assert calls == ["init", "uninit"]


def test_outlook_adapter_never_raises_when_pythoncom_init_fails(monkeypatch):
    """CoInitialize itself failing (no pywin32, or the apartment call
    failing) must return a SendResult like every other failure here, not
    raise out of `send`."""
    fake_pythoncom = types.SimpleNamespace(
        CoInitialize=lambda: (_ for _ in ()).throw(RuntimeError("no pywin32")),
        CoUninitialize=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)

    app = _FakeOutlookApplication()
    adapter = OutlookMailAdapter(dispatch=lambda: app)
    result = adapter.send(to_address="a@b.com", subject="Subj", body="Body")

    assert result.sent is False
    assert result.simulated is False
    assert "Outlook send failed" in result.detail
    assert app.created_items == []


def test_outlook_adapter_writes_attachments_to_temp_files_and_attaches_before_send():
    app = _FakeOutlookApplication()
    adapter = OutlookMailAdapter(dispatch=lambda: app)

    result = adapter.send(
        to_address="candidate@example.com", subject="Subj", body="Body",
        attachments=[("shortlist.zip", b"zip-bytes"), ("second.zip", b"more-bytes")],
    )

    assert result.sent is True
    item = app.created_items[0]
    assert len(item.Attachments.added) == 2
    added_names = [os.path.basename(path) for path in item.Attachments.added]
    assert added_names == ["shortlist.zip", "second.zip"]
    # Cleaned up after a successful send — nothing left on disk.
    for path in item.Attachments.added:
        assert not os.path.exists(path)


def test_outlook_adapter_cleans_up_temp_attachment_files_when_send_fails():
    class _FailingMailItem(_FakeMailItem):
        def Send(self):
            raise RuntimeError("send failed")

    class _FailingApp(_FakeOutlookApplication):
        def CreateItem(self, item_type):
            item = _FailingMailItem()
            self.created_items.append(item)
            return item

    app = _FailingApp()
    adapter = OutlookMailAdapter(dispatch=lambda: app)

    result = adapter.send(
        to_address="a@b.com", subject="Subj", body="Body",
        attachments=[("shortlist.zip", b"zip-bytes")],
    )

    assert result.sent is False
    item = app.created_items[0]
    for path in item.Attachments.added:
        assert not os.path.exists(path)


def test_outlook_adapter_with_no_attachments_leaves_attachments_untouched():
    app = _FakeOutlookApplication()
    adapter = OutlookMailAdapter(dispatch=lambda: app)

    result = adapter.send(to_address="a@b.com", subject="Subj", body="Body")

    assert result.sent is True
    assert app.created_items[0].Attachments.added == []


def test_get_mail_adapter_defaults_to_simulated(monkeypatch):
    monkeypatch.setattr(outlook_adapter.settings, "email_backend", "simulated")
    assert isinstance(get_mail_adapter(), SimulatedMailAdapter)


def test_get_mail_adapter_selects_outlook_when_configured(monkeypatch):
    monkeypatch.setattr(outlook_adapter.settings, "email_backend", "outlook")
    assert isinstance(get_mail_adapter(), OutlookMailAdapter)


def test_get_mail_adapter_falls_back_when_outlook_cannot_be_built(monkeypatch):
    monkeypatch.setattr(outlook_adapter.settings, "email_backend", "outlook")

    class _BrokenAdapter:
        def __init__(self):
            raise RuntimeError("pywin32 not installed")

    monkeypatch.setattr(outlook_adapter, "OutlookMailAdapter", _BrokenAdapter)
    assert isinstance(get_mail_adapter(), SimulatedMailAdapter)
