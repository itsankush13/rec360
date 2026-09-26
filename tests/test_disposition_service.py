"""
Regression coverage for the flaky "oldest/newest first" ordering defect
(docs/plan/04-KNOWN-DEFECTS.md): test_messages_api, test_interviews_api and
test_approvals_api intermittently mis-order two audit rows written back to
back, because both can land on the same datetime.now(timezone.utc) tick and
audit_trail()/similar queries order by created_at alone with no tiebreaker.
"""
from datetime import datetime, timezone
from unittest.mock import patch

from app.db.models import AuditAction
from app.services import disposition_service


def test_audit_events_written_in_the_same_clock_tick_still_order_correctly(db_session):
    frozen = datetime(2026, 1, 1, tzinfo=timezone.utc)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen

    with patch.object(disposition_service, "datetime", _FrozenDatetime):
        first = disposition_service.record_audit(
            db_session, AuditAction.COMMENT_ADDED, summary="first",
        )
        second = disposition_service.record_audit(
            db_session, AuditAction.COMMENT_ADDED, summary="second",
        )

    assert first.created_at < second.created_at

    events = disposition_service.audit_trail(db_session)
    assert [e.summary for e in events[:2]] == ["second", "first"]
