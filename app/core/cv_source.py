"""
CV source resolution — turn a SharePoint/OneDrive link, a UNC path, or a plain
local folder into a list of candidate CV files.

Tier 1 design: no Microsoft Graph, no OAuth, no network call. This works
because the library is already synced to local disk by the OneDrive client —
a SharePoint or OneDrive URL is resolved to that local folder by matching the
decoded tail of the URL against the folders under the machine's OneDrive
sync roots.

`CVSource` is the seam. `SyncedFolderSource` is the only implementation
today. A Graph-backed source can be added later as a second `CVSource`
implementation without touching the API routes or the screen — see
`app/api/discovery.py`.
"""
from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.document_intake import SUPPORTED_EXTENSIONS

SOURCE_LOCAL = "local_path"
SOURCE_UNC = "unc_path"
SOURCE_SHAREPOINT_URL = "sharepoint_url"


class CVSourceResolutionError(Exception):
    """
    A location could not be turned into a local folder.

    `searched_roots` names every OneDrive sync root that was checked, so the
    screen can tell the user exactly where the search looked instead of just
    saying "not found".
    """

    def __init__(self, message: str, searched_roots: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.searched_roots = searched_roots or []


@dataclass
class ResolvedSource:
    """A location that has been turned into a real local folder."""

    root_path: str
    source_kind: str
    original_location: str


@dataclass
class CVFile:
    filename: str
    path: str
    size_bytes: int
    modified_at: datetime
    extension: str


@dataclass
class CVListResult:
    cvs: list[CVFile] = field(default_factory=list)
    skipped_placeholders: int = 0


def _looks_like_url(location: str) -> bool:
    return location.lower().startswith("http://") or location.lower().startswith("https://")


def _looks_like_unc(location: str) -> bool:
    return location.startswith("\\\\") or location.startswith("//")


_SITE_MARKERS = {"personal", "sites", "teams"}


def _max_discardable_prefix(segments: list[str]) -> int:
    """
    How many leading URL-path segments `_resolve_url` may drop before it
    must start matching real folders under a sync root.

    A SharePoint/OneDrive URL's site identity is `personal/<user>` or
    `sites/<name>` — two segments that are never mirrored as literal local
    folders, because the sync client's local root already *is* that
    library. Everything after those two segments is the real, locally
    mirrored path, and shrinking past them starts discarding real library
    structure instead of just the site identity. That is exactly how the
    proven X13 bug happened: a fabricated URL naming an unrelated site
    (`personal/x/Documents/Work/Resume-Screening/CV-Repository`) still
    matched a real folder, because the search kept shrinking until only
    the last segment or two — a generic folder name — happened to exist
    somewhere under a real sync root.
    """
    for index, segment in enumerate(segments):
        if segment.lower() in _SITE_MARKERS:
            return index + 2
    return 0  # No recognised site marker — an unusual shape; require the whole path.


# The Windows attribute bits used to mark a OneDrive placeholder file that has
# no local content yet. FILE_ATTRIBUTE_OFFLINE (0x1000) and
# FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS (0x00400000) both mean "the bytes are
# not on this disk"; either one is enough to call a file cloud-only.
_FILE_ATTRIBUTE_OFFLINE = 0x1000
_FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000


def _is_cloud_placeholder(path: Path) -> bool:
    """
    True if this file's bytes have not been downloaded to this machine.

    Windows-only check. On any other platform, or if the attribute call
    fails for any reason, a file is never treated as a placeholder — the
    only cost of that is one caller doing a real read of a file that turns
    out to be a placeholder, which then reads as an empty or short file.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return False
        return bool(
            attrs & _FILE_ATTRIBUTE_OFFLINE
            or attrs & _FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
        )
    except Exception:
        return False


def _default_sync_roots() -> list[Path]:
    """
    Enumerate this machine's OneDrive sync roots.

    Reliable source: `HKCU\\Software\\Microsoft\\OneDrive\\Accounts\\*`,
    value `UserFolder`. Read-only. Falls back to scanning `%USERPROFILE%`
    for directories starting with "OneDrive" — covers a machine where the
    registry key is missing or unreadable but the folder is still there.
    """
    roots: list[Path] = []

    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Microsoft\OneDrive\Accounts"
            ) as accounts_key:
                index = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(accounts_key, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(accounts_key, subkey_name) as subkey:
                            value, _ = winreg.QueryValueEx(subkey, "UserFolder")
                            candidate = Path(value)
                            if candidate not in roots:
                                roots.append(candidate)
                    except OSError:
                        continue
        except OSError:
            pass

    profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    if profile.is_dir():
        for entry in profile.iterdir():
            if entry.is_dir() and entry.name.startswith("OneDrive") and entry not in roots:
                roots.append(entry)

    return roots


class CVSource(ABC):
    """The seam. A Graph-backed source implements this same interface."""

    @abstractmethod
    def resolve(self, location: str) -> ResolvedSource:
        ...

    @abstractmethod
    def list_cvs(self, resolved: ResolvedSource) -> CVListResult:
        ...


class SyncedFolderSource(CVSource):
    """
    Resolves a location against folders already present on local disk —
    either given directly (local path, UNC path) or matched to a OneDrive
    sync root (SharePoint/OneDrive URL).
    """

    def __init__(self, sync_roots: list[Path] | None = None):
        # Passing sync_roots in lets a test point at a fake sync root
        # instead of this machine's real OneDrive account.
        self._explicit_sync_roots = sync_roots

    def _sync_roots(self) -> list[Path]:
        if self._explicit_sync_roots is not None:
            return self._explicit_sync_roots
        return _default_sync_roots()

    def resolve(self, location: str) -> ResolvedSource:
        stripped = location.strip()
        if not stripped:
            raise CVSourceResolutionError("No location was given.")

        if _looks_like_url(stripped):
            return self._resolve_url(stripped)
        if _looks_like_unc(stripped):
            unc_path = Path(stripped)
            if not unc_path.is_dir():
                raise CVSourceResolutionError(
                    f"'{stripped}' is not a folder this machine can reach on "
                    "the network."
                )
            return ResolvedSource(
                root_path=str(unc_path), source_kind=SOURCE_UNC, original_location=stripped
            )

        path = Path(stripped)
        if not path.is_dir():
            raise CVSourceResolutionError(
                f"'{stripped}' is not a folder on this machine."
            )
        return ResolvedSource(
            root_path=str(path), source_kind=SOURCE_LOCAL, original_location=stripped
        )

    def _resolve_url(self, url: str) -> ResolvedSource:
        roots = self._sync_roots()
        parsed = urlparse(url)
        segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
        if not segments:
            raise CVSourceResolutionError(
                f"'{url}' has no path to match against a synced folder."
            )
        max_start = min(_max_discardable_prefix(segments), len(segments) - 1)

        # Try the longest suffix of the URL path first, shrinking from the
        # left, so a match against the deepest folder wins — but never
        # shrink past the site identity itself (see _max_discardable_prefix),
        # and if more than one root ties for the best (longest) match,
        # refuse rather than silently taking whichever root came first.
        best_start: int | None = None
        matches: list[Path] = []
        for root in roots:
            for start in range(max_start + 1):
                candidate = root
                matched = True
                for segment in segments[start:]:
                    candidate = candidate / segment
                    if not candidate.is_dir():
                        matched = False
                        break
                if matched:
                    if best_start is None or start < best_start:
                        best_start = start
                        matches = [candidate]
                    elif start == best_start:
                        matches.append(candidate)
                    break

        if len(matches) > 1:
            raise CVSourceResolutionError(
                "This link matches more than one folder synced on this machine: "
                + ", ".join(str(m) for m in matches)
                + ". Refusing to guess which one — narrow the link or remove "
                "the sync you did not mean.",
                searched_roots=[str(root) for root in roots],
            )
        if matches:
            return ResolvedSource(
                root_path=str(matches[0]),
                source_kind=SOURCE_SHAREPOINT_URL,
                original_location=url,
            )

        searched = [str(root) for root in roots]
        raise CVSourceResolutionError(
            "Could not match this link to a folder synced on this machine. "
            "The library may not be synced here, or the link names a "
            "different site than what's synced. "
            + (
                f"Searched: {', '.join(searched)}."
                if searched
                else "No OneDrive sync roots were found on this machine."
            ),
            searched_roots=searched,
        )

    def list_cvs(self, resolved: ResolvedSource) -> CVListResult:
        root = Path(resolved.root_path)
        if not root.is_dir():
            raise CVSourceResolutionError(
                f"Resolved folder no longer exists: {resolved.root_path}"
            )

        result = CVListResult()
        for entry in sorted(root.iterdir()):
            if not entry.is_file():
                continue
            extension = entry.suffix.lower()
            if extension not in SUPPORTED_EXTENSIONS:
                continue
            if _is_cloud_placeholder(entry):
                result.skipped_placeholders += 1
                continue
            stat = entry.stat()
            result.cvs.append(
                CVFile(
                    filename=entry.name,
                    path=str(entry.resolve()),
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    extension=extension,
                )
            )
        return result
