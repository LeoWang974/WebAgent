# File purpose: Verifies cross-platform artifact path normalization and host resolution.
# Main declarations: tests cover arbitrary WSL distributions, Windows drives, and Linux hosts.

from app.services.artifact_path_utils import (
    artifact_path_for_host,
    canonical_artifact_path_key,
)


def test_canonical_path_key_accepts_any_wsl_distribution():
    expected = "/home/demo/report.md"

    assert canonical_artifact_path_key(
        r"\\wsl.localhost\Ubuntu-22.04\home\demo\report.md"
    ) == expected
    assert canonical_artifact_path_key(
        r"\\wsl$\Debian\home\demo\report.md"
    ) == expected
    assert canonical_artifact_path_key("/home/demo/report.md") == expected


def test_canonical_path_key_unifies_windows_drive_and_wsl_mount():
    expected = "/mnt/d/reports/final.pptx"

    assert canonical_artifact_path_key(r"D:\Reports\Final.pptx") == expected
    assert canonical_artifact_path_key("/mnt/d/reports/final.pptx") == expected


def test_host_path_uses_configured_wsl_distribution():
    path = artifact_path_for_host(
        "/home/demo/report.md",
        wsl_distribution="Debian",
        host_os="nt",
    )

    assert str(path) == r"\\wsl.localhost\Debian\home\demo\report.md"


def test_host_path_preserves_linux_paths_on_posix():
    assert artifact_path_for_host("/home/demo/report.md", host_os="posix").as_posix() == (
        "/home/demo/report.md"
    )
    assert artifact_path_for_host(
        "/mnt/d/reports/report.md",
        host_os="posix",
    ).as_posix() == "/mnt/d/reports/report.md"
