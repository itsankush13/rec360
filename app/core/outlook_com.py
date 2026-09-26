"""
Tiny COM helper shared by `outlook_adapter.py` and `calendar_adapter.py`.

`SendUsingAccount` set as a plain property is the documented high-level way
to pick the sending account, and it normally works — but it is known to
fail silently or raise on some Outlook builds. The low-level fallback below
(dispid 64209, the real `SendUsingAccount` dispatch id) is a reference
implementation supplied for exactly that case.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SEND_USING_ACCOUNT_DISPID = 64209


def set_send_using_account(item, account) -> bool:
    """Try the plain property first, then the low-level dispid call.

    Returns True once either path succeeds, False if both fail — callers
    must treat False as a failed send, never a silent success.
    """
    try:
        item.SendUsingAccount = account
        return True
    except Exception:
        pass
    try:
        item._oleobj_.Invoke(*(SEND_USING_ACCOUNT_DISPID, 0, 8, 0, account))
        return True
    except Exception:
        return False


def _dispatch_outlook():
    """Isolated so tests can monkeypatch it without pywin32 or a real
    Outlook install being involved."""
    import win32com.client
    return win32com.client.Dispatch("Outlook.Application")


_cached_sender: str | None = None
_cache_populated = False


def resolve_sender_address(explicit: str) -> str | None:
    """The effective Outlook sending identity for THIS machine.

    An explicit setting (`email_sender_address` / `calendar_sender_email`)
    always wins — it is a deliberate override. Otherwise, discover the
    SmtpAddress of the first account in the local Outlook profile's
    `Session.Accounts` — the account this machine is signed in as. That way
    the sender follows whoever is running the app, not a hardcoded person.

    The discovered value is cached for the life of the process, so a guard
    check does not open a new COM connection on every request.

    Returns None when Outlook is not installed, not signed in, or has no
    account. Callers must treat None as an honest "cannot resolve a
    sender" and reject the request — never fall back to a guess.
    """
    if explicit:
        return explicit
    global _cached_sender, _cache_populated
    if _cache_populated:
        return _cached_sender
    try:
        outlook = _dispatch_outlook()
        accounts = list(outlook.Session.Accounts)
        address = str(accounts[0].SmtpAddress) if accounts else None
    except Exception as exc:
        logger.warning("Could not discover a local Outlook sender account: %s", exc)
        address = None
    _cached_sender = address
    _cache_populated = True
    return address


def reset_sender_cache() -> None:
    """Test-only: clears the cached discovery so a test can simulate a
    fresh process."""
    global _cached_sender, _cache_populated
    _cached_sender = None
    _cache_populated = False
