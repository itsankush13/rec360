"""
`set_send_using_account` — the plain-property-then-dispid-fallback helper
shared by `outlook_adapter.py` and `calendar_adapter.py`.

`resolve_sender_address` — the runtime sender resolver behind the dynamic
sending identity: an explicit setting always wins, otherwise the local
Outlook profile's own signed-in account is discovered and cached, so the
product sends as whoever is running it rather than one hardcoded person.
"""
import pytest

from app.core import outlook_com
from app.core.outlook_com import resolve_sender_address, set_send_using_account


@pytest.fixture(autouse=True)
def _clear_sender_cache():
    """Every test starts as if it were a fresh process — otherwise
    whichever test discovers a sender first would leak its cached result
    into every test that runs after it."""
    outlook_com.reset_sender_cache()
    yield
    outlook_com.reset_sender_cache()


class _PlainItem:
    """Plain property assignment succeeds — the common case."""

    def __init__(self):
        self.SendUsingAccount = None


def test_sets_via_the_plain_property_when_it_works():
    item = _PlainItem()
    account = object()

    assert set_send_using_account(item, account) is True
    assert item.SendUsingAccount is account


class _RaisingProperty:
    """Some Outlook builds raise on the plain property; the dispid Invoke
    is then tried as a fallback."""

    def __setattr__(self, name, value):
        if name == "SendUsingAccount":
            raise AttributeError("property rejected on this build")
        super().__setattr__(name, value)

    class _OleObj:
        def __init__(self):
            self.invoked_with = None

        def Invoke(self, *args):
            self.invoked_with = args

    def __init__(self):
        self._oleobj_ = self._OleObj()


def test_falls_back_to_the_dispid_invoke_when_the_property_raises():
    item = _RaisingProperty()
    account = object()

    assert set_send_using_account(item, account) is True
    assert item._oleobj_.invoked_with == (64209, 0, 8, 0, account)


class _BothFail(_RaisingProperty):
    class _OleObj:
        def Invoke(self, *args):
            raise RuntimeError("dispid call also rejected")

    def __init__(self):
        self._oleobj_ = self._OleObj()


def test_reports_failure_when_both_the_property_and_the_dispid_fail():
    item = _BothFail()

    assert set_send_using_account(item, object()) is False


class _FakeAccount:
    def __init__(self, smtp_address):
        self.SmtpAddress = smtp_address


class _FakeOutlookApplication:
    def __init__(self, accounts):
        self.Session = type("Session", (), {"Accounts": accounts})()


def test_resolve_sender_address_explicit_setting_wins(monkeypatch):
    """An explicit setting is a deliberate override — discovery must not
    even run."""
    def _should_never_be_called():
        raise AssertionError("discovery should not run when explicit is set")

    monkeypatch.setattr(outlook_com, "_dispatch_outlook", _should_never_be_called)

    assert resolve_sender_address("ankush.saxena@protivitiglobal.in") == (
        "ankush.saxena@protivitiglobal.in"
    )


def test_resolve_sender_address_discovers_the_signed_in_account_when_blank(monkeypatch):
    app = _FakeOutlookApplication([_FakeAccount("ankush.saxena@protivitiglobal.in")])
    monkeypatch.setattr(outlook_com, "_dispatch_outlook", lambda: app)

    assert resolve_sender_address("") == "ankush.saxena@protivitiglobal.in"


def test_resolve_sender_address_caches_the_discovery(monkeypatch):
    """Discovery runs at most once per process — a guard check must not
    open a fresh COM connection on every request."""
    calls = []

    def _dispatch():
        calls.append(1)
        return _FakeOutlookApplication([_FakeAccount("ankush.saxena@protivitiglobal.in")])

    monkeypatch.setattr(outlook_com, "_dispatch_outlook", _dispatch)

    assert resolve_sender_address("") == "ankush.saxena@protivitiglobal.in"
    assert resolve_sender_address("") == "ankush.saxena@protivitiglobal.in"
    assert len(calls) == 1


def test_resolve_sender_address_is_honest_when_no_account_can_be_found(monkeypatch):
    monkeypatch.setattr(outlook_com, "_dispatch_outlook", lambda: _FakeOutlookApplication([]))

    assert resolve_sender_address("") is None


def test_resolve_sender_address_is_honest_when_outlook_is_unavailable(monkeypatch):
    def _broken_dispatch():
        raise RuntimeError("Outlook is not installed")

    monkeypatch.setattr(outlook_com, "_dispatch_outlook", _broken_dispatch)

    assert resolve_sender_address("") is None
