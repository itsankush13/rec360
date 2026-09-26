"""
The subject-tagging contract — B10 (outbound half).

A second, parallel piece of work reads Outlook replies and classifies them
back onto the record they were about (a campaign, or one candidate inside
it). The only thing connecting an outbound message to a future reply is the
subject line, so every outbound email must carry a small machine-readable
tag, and every place that composes a subject must build that tag the same
way — hence one function, used everywhere, rather than four call sites each
formatting the string by hand and drifting apart.

Fixed shape, matched on the reading side by:
    \\[REF-([0-9a-fA-F-]{36})(?::([0-9a-fA-F-]{36}))?\\]

  * " [REF-{campaign_id}]"                — about the whole campaign
  * " [REF-{campaign_id}:{candidate_id}]" — about one candidate in it

`campaign_id`/`candidate_id` are the real UUID primary keys (36-character,
hyphenated `str(uuid.uuid4())` — see `app.db.models._uuid`), not a display
name or a shortened id, because the reader's regex is anchored to that
length.
"""
from __future__ import annotations


def ref_tag(campaign_id: str, candidate_id: str | None = None) -> str:
    """
    The bracketed reference to append to an outbound subject line.

    Always leads with a space, so callers just concatenate it onto whatever
    subject they already built: `subject + ref_tag(campaign_id)`.
    """
    if candidate_id:
        return f" [REF-{campaign_id}:{candidate_id}]"
    return f" [REF-{campaign_id}]"
