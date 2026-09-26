"""
Local Outlook mail adapter — B10.

Real transmission is opt-in and off by default: `settings.email_backend` must
be set to "outlook" (a real shell/env value, same opt-in shape `CLAUDE.md`
requires for `QUEUE_BACKEND`) before a single message leaves this process.
Anything else — the default "simulated", or "outlook" requested where
`pywin32`/COM is unavailable — goes through `SimulatedMailAdapter`, which is
byte-for-byte the product's pre-existing behavior: an honest audit row, no
transmission.

`OutlookMailAdapter` was built and unit-tested this session against a fake COM
double (`tests/test_outlook_adapter.py`) — it has never been exercised against
a real, signed-in Outlook profile, because none was confirmed available in
this environment. Treat it as unverified against a live mailbox until someone
runs it against one.

Also unverified against a live mailbox, added the same session as the CC
support below:

  * `settings.email_sender_address` picks the Outlook account a real send
    goes out from, the same way `calendar_sender_email` does for
    `app.core.calendar_adapter`'s invites — via `SendUsingAccount` on
    `outlook.Session.Accounts`. If it is set but no signed-in account
    matches, the send fails honestly (`sent=False, simulated=False`)
    rather than silently going out from whatever Outlook's own default
    account happens to be.
  * `cc_address` is threaded through to `mail.CC`, mirroring `mail.To`.
  * `pythoncom.CoInitialize()`/`CoUninitialize()` wrap the real COM call.
    FastAPI runs a sync route handler in a worker thread, and COM requires
    each thread that touches it to initialize its own apartment first —
    without this, a real send from inside a request could fail or behave
    unpredictably in a way a single-threaded script would never surface.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import shutil
import tempfile

from app.core.config import settings
from app.core.outlook_com import set_send_using_account

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class SendResult:
    sent: bool
    simulated: bool
    detail: str


class MailAdapter:
    """Interface. `send` must never raise — callers always get a SendResult."""

    def send(
        self, *, to_address: str, subject: str, body: str,
        cc_address: str | None = None,
        attachments: list[tuple[str, bytes]] | None = None,
        html_body: str | None = None,
    ) -> SendResult:
        raise NotImplementedError


class SimulatedMailAdapter(MailAdapter):
    """Default. Records intent, transmits nothing."""

    def send(
        self, *, to_address: str, subject: str, body: str,
        cc_address: str | None = None,
        attachments: list[tuple[str, bytes]] | None = None,
        html_body: str | None = None,
    ) -> SendResult:
        detail = f"Simulated — no message transmitted to {to_address}."
        if attachments:
            names = ", ".join(name for name, _ in attachments)
            detail += f" Attachment(s): {names}."
        return SendResult(sent=False, simulated=True, detail=detail)


def _dispatch_outlook():
    """
    Isolated in its own function so tests can substitute a fake COM object
    (`OutlookMailAdapter(dispatch=fake)`) without pywin32 or a real Outlook
    install being involved.
    """
    import win32com.client
    return win32com.client.Dispatch("Outlook.Application")


class OutlookMailAdapter(MailAdapter):
    """
    Sends through a local, signed-in Outlook desktop profile via COM
    automation. See the module docstring: unverified against a real mailbox.
    """

    def __init__(self, dispatch=_dispatch_outlook):
        self._dispatch = dispatch

    def send(
        self, *, to_address: str, subject: str, body: str,
        cc_address: str | None = None,
        attachments: list[tuple[str, bytes]] | None = None,
        html_body: str | None = None,
    ) -> SendResult:
        # FastAPI runs a sync route handler in a worker thread, and COM
        # requires each thread that touches it to initialize its own
        # apartment first — skip this and a real (non-simulated) send can
        # fail or misbehave in a way that never shows up in a single-threaded
        # script. CoInitialize is attempted on its own so a failure there
        # (no pywin32, or the apartment call itself failing) still returns a
        # SendResult rather than raising, same as every other failure here.
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception as exc:
            logger.warning("Outlook send failed: %s", exc)
            return SendResult(
                sent=False, simulated=False,
                detail=f"Outlook send failed: {exc}",
            )
        temp_dir: str | None = None
        try:
            outlook = self._dispatch()
            mail = outlook.CreateItem(0)  # olMailItem
            mail.To = to_address
            if cc_address:
                mail.CC = cc_address
            mail.Subject = subject
            mail.Body = body
            if html_body:
                # HTMLBody takes precedence over Body in Outlook once set;
                # `body` is kept as the plain-text fallback recorded above.
                mail.HTMLBody = html_body
            # Outlook COM attaches from a file path, not bytes. Each
            # attachment is written under one temp directory (so its
            # filename reaches Outlook unchanged), added before Send(), and
            # removed in the `finally` below — including on a failed send,
            # so a broken send never leaks a temp file.
            if attachments:
                temp_dir = tempfile.mkdtemp(prefix="tis-mail-")
                for filename, content in attachments:
                    path = os.path.join(temp_dir, filename)
                    with open(path, "wb") as handle:
                        handle.write(content)
                    mail.Attachments.Add(path)
            if settings.email_sender_address:
                matching = next(
                    (account for account in outlook.Session.Accounts
                     if str(account.SmtpAddress).lower()
                     == settings.email_sender_address.lower()),
                    None,
                )
                if matching is None:
                    return SendResult(
                        sent=False, simulated=False,
                        detail=(
                            "Configured Outlook sender account is not "
                            "signed in; message was not sent."
                        ),
                    )
                if not set_send_using_account(mail, matching):
                    return SendResult(
                        sent=False, simulated=False,
                        detail="Could not set the Outlook sender account; message was not sent.",
                    )
            mail.Send()
            return SendResult(
                sent=True, simulated=False,
                detail=f"Sent via local Outlook to {to_address}.",
            )
        except Exception as exc:
            logger.warning("Outlook send failed: %s", exc)
            return SendResult(
                sent=False, simulated=False,
                detail=f"Outlook send failed: {exc}",
            )
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
            pythoncom.CoUninitialize()


def get_mail_adapter() -> MailAdapter:
    if settings.email_backend != "outlook":
        return SimulatedMailAdapter()
    try:
        return OutlookMailAdapter()
    except Exception as exc:
        logger.warning(
            "email_backend=outlook but the adapter could not be constructed (%s); "
            "falling back to simulated.", exc,
        )
        return SimulatedMailAdapter()
