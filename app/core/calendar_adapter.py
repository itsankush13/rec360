"""
Local Outlook calendar adapter — B11.

Same opt-in shape as `app.core.outlook_adapter` (B10): `settings.calendar_backend`
must be a real shell/env value of "outlook" before any invite leaves this
process. Anything else — the default "simulated", or "outlook" requested
where `pywin32`/COM is unavailable — goes through `SimulatedCalendarAdapter`:
an honest audit row, no invite sent, no attendee calendar touched.

`OutlookCalendarAdapter` is unit-tested against a fake COM double
(`tests/test_calendar_adapter.py`) only. It has never been exercised against
a real, signed-in Outlook profile — treat it as unverified against a live
mailbox/calendar until someone runs it against one, exactly like B10's mail
adapter.
"""
from __future__ import annotations

import dataclasses
import logging
from datetime import datetime

from app.core.config import settings
from app.core.outlook_com import set_send_using_account

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class InviteResult:
    sent: bool
    simulated: bool
    detail: str


class CalendarAdapter:
    """Interface. `send_invite` must never raise — callers always get an InviteResult."""

    def send_invite(
        self, *, subject: str, start: datetime, duration_minutes: int,
        location: str, required_attendees: list[str], optional_attendees: list[str],
        body: str = "",
    ) -> InviteResult:
        raise NotImplementedError


class SimulatedCalendarAdapter(CalendarAdapter):
    """Default. Records intent, blocks no one's calendar."""

    def send_invite(
        self, *, subject: str, start: datetime, duration_minutes: int,
        location: str, required_attendees: list[str], optional_attendees: list[str],
        body: str = "",
    ) -> InviteResult:
        count = len(required_attendees) + len(optional_attendees)
        return InviteResult(
            sent=False, simulated=True,
            detail=f"Simulated — no calendar invite sent to {count} attendee(s).",
        )


def _dispatch_outlook():
    """
    Isolated in its own function so tests can substitute a fake COM object
    (`OutlookCalendarAdapter(dispatch=fake)`) without pywin32 or a real
    Outlook install being involved.
    """
    import win32com.client
    return win32com.client.Dispatch("Outlook.Application")


class OutlookCalendarAdapter(CalendarAdapter):
    """
    Creates a meeting request through a local, signed-in Outlook desktop
    profile via COM automation. Required attendees (interviewer panel and
    candidate) block their calendars once the invite is sent; optional
    attendees do not. See the module docstring: unverified against a real
    mailbox/calendar.
    """

    def __init__(self, dispatch=_dispatch_outlook):
        self._dispatch = dispatch

    def send_invite(
        self, *, subject: str, start: datetime, duration_minutes: int,
        location: str, required_attendees: list[str], optional_attendees: list[str],
        body: str = "",
    ) -> InviteResult:
        # Same reasoning as OutlookMailAdapter.send: FastAPI runs a sync
        # route handler in a worker thread, and COM requires each thread to
        # initialize its own apartment before touching it.
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception as exc:
            logger.warning("Outlook calendar invite failed: %s", exc)
            return InviteResult(
                sent=False, simulated=False,
                detail=f"Outlook calendar invite failed: {exc}",
            )
        try:
            outlook = self._dispatch()
            appointment = outlook.CreateItem(1)  # olAppointmentItem
            appointment.MeetingStatus = 1  # olMeeting — turns it into an invite
            appointment.Subject = subject
            appointment.Start = start
            appointment.Duration = duration_minutes
            appointment.Location = location
            appointment.Body = body
            if settings.calendar_sender_email:
                matching = next((account for account in outlook.Session.Accounts
                                 if str(account.SmtpAddress).lower() == settings.calendar_sender_email.lower()), None)
                if matching is None:
                    return InviteResult(sent=False, simulated=False,
                                        detail="Configured Outlook sender account is not signed in; invite was not sent.")
                if not set_send_using_account(appointment, matching):
                    return InviteResult(
                        sent=False, simulated=False,
                        detail="Could not set the Outlook sender account; invite was not sent.",
                    )
            for address in required_attendees:
                recipient = appointment.Recipients.Add(address)
                recipient.Type = 1  # olRequired
            for address in optional_attendees:
                recipient = appointment.Recipients.Add(address)
                recipient.Type = 2  # olOptional
            appointment.Send()
            count = len(required_attendees) + len(optional_attendees)
            return InviteResult(
                sent=True, simulated=False,
                detail=f"Invite sent via local Outlook to {count} attendee(s).",
            )
        except Exception as exc:
            logger.warning("Outlook calendar invite failed: %s", exc)
            return InviteResult(
                sent=False, simulated=False,
                detail=f"Outlook calendar invite failed: {exc}",
            )
        finally:
            pythoncom.CoUninitialize()


def get_calendar_adapter() -> CalendarAdapter:
    if settings.calendar_backend != "outlook":
        return SimulatedCalendarAdapter()
    try:
        return OutlookCalendarAdapter()
    except Exception as exc:
        logger.warning(
            "calendar_backend=outlook but the adapter could not be constructed "
            "(%s); falling back to simulated.", exc,
        )
        return SimulatedCalendarAdapter()
