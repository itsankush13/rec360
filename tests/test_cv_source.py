"""
Tier 1 CV source resolver — no Microsoft Graph, no network. A location
(local path, UNC path, or SharePoint/OneDrive URL) is resolved to a folder
already synced to local disk, then listed for candidate CV files.
"""
from pathlib import Path

import pytest

from app.core.cv_source import (
    CVSourceResolutionError,
    SOURCE_LOCAL,
    SOURCE_SHAREPOINT_URL,
    SOURCE_UNC,
    SyncedFolderSource,
)


def test_resolves_a_local_absolute_path(tmp_path):
    source = SyncedFolderSource()

    resolved = source.resolve(str(tmp_path))

    assert resolved.root_path == str(tmp_path)
    assert resolved.source_kind == SOURCE_LOCAL


def test_accepts_a_unc_path_that_exists(monkeypatch):
    """X16: a UNC path is checked for existence exactly like a local path.

    No real network share is available in this environment, so the
    filesystem check itself is faked here — this proves the code path, not
    that a real UNC share resolves correctly (that still needs a real
    share, per docs/plan/04-KNOWN-DEFECTS.md's X16).
    """
    monkeypatch.setattr(Path, "is_dir", lambda self: True)
    source = SyncedFolderSource()

    resolved = source.resolve(r"\\fileserver\share\CVs")

    assert resolved.source_kind == SOURCE_UNC
    assert resolved.root_path == r"\\fileserver\share\CVs"


def test_a_unc_path_that_does_not_exist_gets_the_same_honest_error_as_local(monkeypatch):
    monkeypatch.setattr(Path, "is_dir", lambda self: False)
    source = SyncedFolderSource()

    with pytest.raises(CVSourceResolutionError) as excinfo:
        source.resolve(r"\\fileserver\share\Missing")

    assert "not a folder" in excinfo.value.message.lower()


def test_resolves_a_sharepoint_url_against_a_fake_sync_root(tmp_path):
    sync_root = tmp_path / "OneDrive - Fake Tenant"
    target = sync_root / "Documents" / "CV Repository"
    target.mkdir(parents=True)

    source = SyncedFolderSource(sync_roots=[sync_root])

    resolved = source.resolve(
        "https://faketenant-my.sharepoint.com/personal/alice_faketenant_onmicrosoft_com/"
        "Documents/CV%20Repository"
    )

    assert resolved.source_kind == SOURCE_SHAREPOINT_URL
    assert resolved.root_path == str(target)


def test_a_fabricated_url_naming_a_different_site_does_not_match_by_tail_alone(tmp_path):
    """
    Reproduces the X13 bug by hand: a URL naming a site/user that was never
    synced still matched a real folder, because the old shrink-from-the-left
    search kept dropping leading segments until only a generic trailing
    folder name happened to exist somewhere under a real sync root.
    """
    sync_root = tmp_path / "OneDrive - Real Tenant"
    (sync_root / "Actual" / "Path" / "CV-Repository").mkdir(parents=True)
    source = SyncedFolderSource(sync_roots=[sync_root])

    with pytest.raises(CVSourceResolutionError):
        source.resolve(
            "https://realtenant-my.sharepoint.com/personal/x/"
            "Documents/Work/Resume-Screening/CV-Repository"
        )


def test_two_synced_roots_matching_the_same_tail_is_refused_as_ambiguous(tmp_path):
    root_a = tmp_path / "OneDrive - Tenant A"
    root_b = tmp_path / "OneDrive - Tenant B"
    (root_a / "Documents" / "CV Repository").mkdir(parents=True)
    (root_b / "Documents" / "CV Repository").mkdir(parents=True)
    source = SyncedFolderSource(sync_roots=[root_a, root_b])

    with pytest.raises(CVSourceResolutionError) as excinfo:
        source.resolve(
            "https://either-my.sharepoint.com/personal/someone/"
            "Documents/CV%20Repository"
        )

    assert "more than one" in excinfo.value.message.lower()


def test_a_deeper_more_specific_root_wins_over_a_shallower_one_without_ambiguity(tmp_path):
    """The longest (most specific) match still wins outright when only one
    root achieves it — ambiguity is only for a genuine tie."""
    specific_root = tmp_path / "OneDrive - Specific"
    (specific_root / "Documents" / "CV Repository").mkdir(parents=True)
    shallow_root = tmp_path / "OneDrive - Shallow"
    (shallow_root / "CV Repository").mkdir(parents=True)
    source = SyncedFolderSource(sync_roots=[specific_root, shallow_root])

    resolved = source.resolve(
        "https://tenant-my.sharepoint.com/personal/someone/Documents/CV%20Repository"
    )

    assert resolved.root_path == str(specific_root / "Documents" / "CV Repository")


def test_unresolvable_url_names_the_searched_roots(tmp_path):
    sync_root = tmp_path / "OneDrive - Fake Tenant"
    sync_root.mkdir()
    source = SyncedFolderSource(sync_roots=[sync_root])

    with pytest.raises(CVSourceResolutionError) as excinfo:
        source.resolve("https://faketenant.sharepoint.com/sites/NotSynced/Shared%20Documents")

    assert str(sync_root) in excinfo.value.searched_roots
    assert "synced" in excinfo.value.message.lower()


def test_list_cvs_filters_by_supported_extensions(tmp_path):
    """
    Only reads `SUPPORTED_EXTENSIONS` from `app.core.document_intake` — never
    a copy — so this list tracks that module even as it changes.
    """
    from app.core.document_intake import SUPPORTED_EXTENSIONS

    (tmp_path / "resume.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "resume.docx").write_bytes(b"fake docx bytes")
    (tmp_path / "notes.txt").write_text("not a CV format")

    source = SyncedFolderSource()
    resolved = source.resolve(str(tmp_path))

    listing = source.list_cvs(resolved)

    filenames = {cv.filename for cv in listing.cvs}
    assert filenames == {
        f.name for f in tmp_path.iterdir()
        if f.suffix.lower() in SUPPORTED_EXTENSIONS
    }
    assert "notes.txt" not in filenames
    assert listing.skipped_placeholders == 0


def test_list_cvs_reports_placeholder_files_separately(tmp_path, monkeypatch):
    (tmp_path / "downloaded.pdf").write_bytes(b"%PDF-1.4 fake")
    (tmp_path / "cloud_only.pdf").write_bytes(b"")

    import app.core.cv_source as cv_source

    def fake_is_placeholder(path):
        return path.name == "cloud_only.pdf"

    monkeypatch.setattr(cv_source, "_is_cloud_placeholder", fake_is_placeholder)

    source = cv_source.SyncedFolderSource()
    resolved = source.resolve(str(tmp_path))

    listing = source.list_cvs(resolved)

    assert [cv.filename for cv in listing.cvs] == ["downloaded.pdf"]
    assert listing.skipped_placeholders == 1
