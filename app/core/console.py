"""Console encoding safety.

A Windows console hands Python a cp1252 stdout. Any log line carrying a glyph
outside that codepage raises UnicodeEncodeError at the point of the print. When
that print sits inside an except block, the original error is replaced by an
encoding error and the whole request fails.

`configure_utf8_output` switches a stream to UTF-8 with replacement, so a log
line can never be the reason a request fails.
"""

from typing import Any

__all__ = ["configure_utf8_output"]


def configure_utf8_output(stream: Any) -> bool:
    """Reconfigure `stream` to UTF-8 with error replacement.

    Returns True when the stream was changed. Returns False when the stream is
    already UTF-8, or cannot be reconfigured — a pytest capture object and a
    plain file-like object both fall into that second case, and neither is a
    problem worth raising over.
    """
    encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
    if encoding == "utf8":
        return False
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return False
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError, AttributeError):
        return False
    return True
