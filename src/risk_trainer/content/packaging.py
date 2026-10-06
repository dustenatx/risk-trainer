"""The Lambda deployment package (PRD R14): dependencies plus approved scenarios only.

The zip is deterministic (sorted entries, fixed timestamps and permissions), so an unchanged
build produces the same bytes and Terraform sees no code change.
"""

import zipfile
from pathlib import Path

from risk_trainer.content.repository import SCENARIOS_DIR, publishable_reports

PACKAGED_CONTENT_DIR = "content"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
FILE_MODE = 0o644
SKIPPED_DIRS = frozenset({"__pycache__"})


class PackagingError(Exception):
    """The package can't be built safely."""


def approved_files(content_dir: Path) -> list[Path]:
    """Approved scenario files. Raises ScenarioInvalid if any file in scenarios/ is invalid."""
    return sorted(report.path for report in publishable_reports(content_dir))


def dependency_files(site_packages: Path) -> list[tuple[str, Path]]:
    """Every regular file under site_packages, as (archive name, path), sorted."""
    entries = []
    for path in sorted(site_packages.rglob("*")):
        relative = path.relative_to(site_packages)
        if path.is_symlink():
            raise PackagingError(f"symlinks are not packaged: {relative}")
        if not path.is_file() or SKIPPED_DIRS.intersection(relative.parts):
            continue
        if relative.parts[0] == PACKAGED_CONTENT_DIR:
            raise PackagingError(f"{relative} would collide with the packaged content")
        entries.append((relative.as_posix(), path))
    return entries


def build_zip(content_dir: Path, out: Path, site_packages: Path | None = None) -> list[str]:
    """Write the package to `out` and return the packaged scenario names.

    Content is checked before anything is written, so a failed build leaves no zip behind.
    """
    scenarios = [
        (f"{PACKAGED_CONTENT_DIR}/{SCENARIOS_DIR}/{path.name}", path)
        for path in approved_files(content_dir)
    ]
    entries = dependency_files(site_packages) if site_packages is not None else []
    entries += scenarios

    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in entries:
            info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
            info.external_attr = FILE_MODE << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    partial.replace(out)
    return [name for name, _ in scenarios]
