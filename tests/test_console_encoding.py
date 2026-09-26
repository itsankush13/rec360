"""A Windows console defaults to cp1252. A log line that carries a non-ASCII
character must never abort a request.

`app/core/pipeline.py` runs inside the POST /api/campaigns/screen route and
printed check and cross glyphs. On a cp1252 stdout that raised
UnicodeEncodeError inside the except block, so the whole screening returned 500.
"""

import io
import pathlib

import pytest

from app.core.console import configure_utf8_output


def _cp1252_stream() -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")


def test_a_cp1252_stream_fails_without_configuration():
    stream = _cp1252_stream()
    with pytest.raises(UnicodeEncodeError):
        stream.write("\u2713")
        stream.flush()


def test_configure_utf8_output_makes_unicode_safe():
    stream = _cp1252_stream()
    assert configure_utf8_output(stream) is True
    stream.write("\u2713 ok \u2192 done \U0001f511")
    stream.flush()
    assert stream.encoding.lower().replace("-", "") == "utf8"


def test_configure_utf8_output_leaves_a_utf8_stream_alone():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    assert configure_utf8_output(stream) is False


def test_configure_utf8_output_tolerates_a_stream_without_reconfigure():
    class Captured:
        encoding = "cp1252"

    assert configure_utf8_output(Captured()) is False


def test_configure_utf8_output_tolerates_a_stream_with_no_encoding():
    class Bare:
        pass

    assert configure_utf8_output(Bare()) is False


@pytest.mark.parametrize(
    "module",
    ["app/core/pipeline.py", "app/main.py"],
)
def test_request_path_modules_print_only_ascii(module):
    source = pathlib.Path(module).read_text(encoding="utf-8")
    offenders = [
        f"{module}:{number}: {line.strip()}"
        for number, line in enumerate(source.splitlines(), 1)
        if ("print(" in line or "logger." in line)
        and any(ord(character) > 127 for character in line)
    ]
    assert offenders == [], "\n".join(offenders)


def test_main_configures_console_encoding_at_import():
    source = pathlib.Path("app/main.py").read_text(encoding="utf-8")
    assert "configure_utf8_output" in source


def test_manage_tenants_configures_console_encoding_at_import():
    source = pathlib.Path("app/core/manage_tenants.py").read_text(encoding="utf-8")
    assert "configure_utf8_output" in source
