# File purpose: Provides shared, platform-aware normalization for artifact filesystem paths.
# Main declarations: canonical_artifact_path_key creates stable dedupe keys;
# artifact_path_for_host resolves Linux/WSL paths on the current host.

import os
import re
from pathlib import Path

_WSL_UNC_RE = re.compile(
    r"^//(?:wsl\.localhost|wsl\$)/[^/]+/(?P<linux_path>.*)$",
    re.IGNORECASE,
)
_WINDOWS_DRIVE_RE = re.compile(r"^(?P<drive>[a-zA-Z]):/(?P<path>.*)$")
_WSL_MOUNT_RE = re.compile(r"^/mnt/(?P<drive>[a-zA-Z])/(?P<path>.*)$")


def _clean_path(value: str | Path) -> str:
    return str(value).strip().strip(".,;:)]}\"'").replace("\\", "/")


def canonical_artifact_path_key(path: str | Path) -> str:
    """Return one case-insensitive key for Windows, WSL UNC, and Linux paths."""

    value = _clean_path(path)
    wsl_match = _WSL_UNC_RE.match(value)
    if wsl_match:
        return "/" + wsl_match.group("linux_path").lower()
    drive_match = _WINDOWS_DRIVE_RE.match(value)
    if drive_match:
        return (
            f"/mnt/{drive_match.group('drive').lower()}/"
            f"{drive_match.group('path').lower()}"
        )
    return value.lower()


def artifact_path_for_host(
    raw_path: str,
    *,
    wsl_distribution: str | None = None,
    host_os: str | None = None,
) -> Path:
    """Resolve a reported artifact path without assuming a specific WSL distro."""

    cleaned = raw_path.strip().strip(".,;:)]}\"'")
    normalized = cleaned.replace("\\", "/")
    current_os = host_os or os.name

    mount_match = _WSL_MOUNT_RE.match(normalized)
    if current_os == "nt" and mount_match:
        drive = mount_match.group("drive").upper()
        rest = mount_match.group("path").replace("/", "\\")
        return Path(f"{drive}:\\{rest}")

    if current_os == "nt" and normalized.startswith("/home/"):
        distribution = (wsl_distribution or "Ubuntu").strip() or "Ubuntu"
        linux_path = normalized.lstrip("/").replace("/", "\\")
        return Path(f"\\\\wsl.localhost\\{distribution}") / linux_path

    return Path(cleaned)


__all__ = ["artifact_path_for_host", "canonical_artifact_path_key"]
