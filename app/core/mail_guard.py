"""
Shared outbound-recipient allowlist for real Outlook mail — B10 hardening.

`app/api/messages.py`, `app/api/reports.py` and `app/api/offers.py` each pass
a caller-supplied recipient straight to `outlook_adapter.get_mail_adapter().send`.
With `settings.email_backend == "outlook"` that is a real send to whatever
address was typed into the UI. `app/api/interviews.py` already restricts its
calendar invites to an approved demo list; this module is the same rule
applied to mail, and the ONE list both paths share (interviews.py imports it
back from here instead of keeping a second copy).

Only active when `settings.email_backend == "outlook"`. Simulated sends stay
free of any address restriction, because demos and tests rely on sending to
whatever candidate/recruiter address they are given.
"""
from __future__ import annotations

from fastapi import HTTPException

from app.core.config import settings

# The signed-in machine owner's mailbox is also the demo candidate proxy.
SELF_TEST_RECIPIENT = "subhadeep.m@protivitiglobal.in"

DEMO_CO_MANAGERS = frozenset({
    "daipayan.r@protivitiglobal.in", "ankush.saxena@protivitiglobal.in",
})
DEMO_RECIPIENTS = frozenset({
    "chiranjib.sarma@protivitiglobal.in", "preetam.c@protivitiglobal.me",
    "daipayan.r@protivitiglobal.in", "ankush.saxena@protivitiglobal.in",
    SELF_TEST_RECIPIENT,
})

APPROVED_MAIL_RECIPIENTS = DEMO_CO_MANAGERS | DEMO_RECIPIENTS | {SELF_TEST_RECIPIENT}


def ensure_approved_mail_recipients(*, to_address: str, cc_address: str | None = None) -> None:
    """Raise HTTP 422 if any real recipient is not on the approved list.

    No-op when `email_backend` is not "outlook" — simulated sends are
    unrestricted.
    """
    if settings.email_backend != "outlook":
        return
    for address in (to_address, cc_address):
        if not address:
            continue
        if address.strip().lower() not in APPROVED_MAIL_RECIPIENTS:
            raise HTTPException(
                status_code=422,
                detail=f"'{address}' is not an approved recipient for a real Outlook send.",
            )
