"""R14 — the build packages approved scenarios only, and fails on any invalid approved one."""

import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from risk_trainer.cli.main import app
from risk_trainer.content.packaging import PackagingError, build_zip
from risk_trainer.domain.errors import ScenarioInvalid
from tests.helpers import REPO_ROOT, WriteScenario, approved

runner = CliRunner()


def names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


@pytest.fixture
def mixed_tree(content_dir: Path, write_scenario: WriteScenario, rt001: dict[str, Any]) -> Path:
    """One approved, one retired (both in scenarios/) and one draft."""
    write_scenario(approved(rt001, "rt-101-approved"), "scenarios")
    retired = approved(rt001, "rt-102-retired")
    retired["status"] = "retired"
    write_scenario(retired, "scenarios")
    draft = {**rt001, "id": "rt-103-draft"}
    write_scenario(draft, "drafts")
    return content_dir


def test_r14_packages_only_approved(mixed_tree: Path, tmp_path: Path) -> None:
    out = tmp_path / "dist" / "lambda.zip"
    packaged = build_zip(mixed_tree, out)
    assert packaged == ["content/scenarios/rt-101-approved.yaml"]
    assert names(out) == ["content/scenarios/rt-101-approved.yaml"]


def test_r14_packaged_file_is_byte_identical(mixed_tree: Path, tmp_path: Path) -> None:
    out = tmp_path / "lambda.zip"
    build_zip(mixed_tree, out)
    source = (mixed_tree / "scenarios" / "rt-101-approved.yaml").read_bytes()
    with zipfile.ZipFile(out) as archive:
        assert archive.read("content/scenarios/rt-101-approved.yaml") == source


def test_r14_invalid_approved_scenario_fails_the_build(
    mixed_tree: Path, write_scenario: WriteScenario, rt001: dict[str, Any], tmp_path: Path
) -> None:
    broken = approved(rt001, "rt-104-broken")
    broken["findings"] = broken["findings"][:2]
    write_scenario(broken, "scenarios")
    out = tmp_path / "lambda.zip"
    with pytest.raises(ScenarioInvalid):
        build_zip(mixed_tree, out)
    assert not out.exists(), "a failed build writes no package"


def test_r14_invalid_draft_does_not_block_the_build(
    mixed_tree: Path, write_scenario: WriteScenario, tmp_path: Path
) -> None:
    write_scenario("id: rt-105-junk\n", "drafts", "rt-105-junk.yaml")
    assert build_zip(mixed_tree, tmp_path / "lambda.zip") == [
        "content/scenarios/rt-101-approved.yaml"
    ]


def test_r14_includes_dependencies_and_skips_bytecode(mixed_tree: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    (site / "pkg" / "__pycache__").mkdir(parents=True)
    (site / "pkg" / "__init__.py").write_text("x = 1\n")
    (site / "pkg" / "__pycache__" / "__init__.cpython-314.pyc").write_bytes(b"\0")
    out = tmp_path / "lambda.zip"
    build_zip(mixed_tree, out, site)
    assert names(out) == ["pkg/__init__.py", "content/scenarios/rt-101-approved.yaml"]


def test_r14_dependency_named_content_is_refused(mixed_tree: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    (site / "content" / "scenarios").mkdir(parents=True)
    (site / "content" / "scenarios" / "rt-999-sneaky.yaml").write_text("id: x\n")
    with pytest.raises(PackagingError, match="collide"):
        build_zip(mixed_tree, tmp_path / "lambda.zip", site)


def test_r14_symlinks_are_refused(mixed_tree: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "link.py").symlink_to(tmp_path / "elsewhere.py")
    with pytest.raises(PackagingError, match="symlinks"):
        build_zip(mixed_tree, tmp_path / "lambda.zip", site)


def test_r14_zip_is_reproducible(mixed_tree: Path, tmp_path: Path) -> None:
    first, second = tmp_path / "a.zip", tmp_path / "b.zip"
    build_zip(mixed_tree, first)
    build_zip(mixed_tree, second)
    assert first.read_bytes() == second.read_bytes()


def test_r14_cli_package(mixed_tree: Path, tmp_path: Path) -> None:
    out = tmp_path / "lambda.zip"
    result = runner.invoke(app, ["package", "--out", str(out), "--content-dir", str(mixed_tree)])
    assert result.exit_code == 0, result.output
    assert "Packaged content/scenarios/rt-101-approved.yaml" in result.output
    assert "1 approved scenario(s)" in result.output


def test_r14_cli_fails_on_invalid_approved(
    mixed_tree: Path, tmp_path: Path, write_scenario: WriteScenario, rt001: dict[str, Any]
) -> None:
    broken = approved(rt001, "rt-104-broken")
    broken["expert_rationale"] = None
    write_scenario(broken, "scenarios")
    out = tmp_path / "lambda.zip"
    result = runner.invoke(app, ["package", "--out", str(out), "--content-dir", str(mixed_tree)])
    assert result.exit_code == 1
    assert "no package was written" in result.output
    assert "rt-104-broken" in result.output
    assert not out.exists()


def test_r14_cli_missing_site_packages(mixed_tree: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["package", "--out", str(tmp_path / "x.zip"), "--site-packages", str(tmp_path / "nope")],
    )
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_r14_makefile_package_target_uses_rt_package() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "uv export --locked --no-dev" in makefile
    assert "--python-platform aarch64-manylinux2014 --python-version 3.14" in makefile
    assert "rt package --site-packages" in makefile


def test_r14_live_content_packages(tmp_path: Path) -> None:
    """The repository's own approved scenarios package cleanly (what CI deploys)."""
    packaged = build_zip(REPO_ROOT / "content", tmp_path / "lambda.zip")
    approved_ids = {
        yaml.safe_load(p.read_text(encoding="utf-8"))["id"]
        for p in (REPO_ROOT / "content" / "scenarios").glob("*.yaml")
        if yaml.safe_load(p.read_text(encoding="utf-8"))["status"] == "approved"
    }
    assert {Path(name).stem for name in packaged} == approved_ids
