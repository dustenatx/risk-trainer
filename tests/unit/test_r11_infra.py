"""R11 — infrastructure as code: S3 remote state with native locking, tagged resources."""

import re
from pathlib import Path

import pytest

from tests.helpers import REPO_ROOT, hcl_blocks

INFRA = REPO_ROOT / "infra"
TF_FILES = sorted(p for p in INFRA.rglob("*.tf") if ".terraform" not in p.parts)


def terraform_roots() -> list[Path]:
    roots = {
        p.parent for p in TF_FILES if hcl_blocks(p.read_text(encoding="utf-8"), r"terraform\s*\{")
    }
    return sorted(roots)


def test_r11_infra_has_terraform() -> None:
    assert (INFRA / "bootstrap").is_dir()
    assert terraform_roots(), "no Terraform root modules under infra/"


@pytest.mark.parametrize("root", terraform_roots(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_r11_s3_backend_uses_native_lockfile(root: Path) -> None:
    text = "\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.tf"))
    (backend,) = hcl_blocks(text, r'backend\s+"s3"\s*\{')
    assert re.search(r"use_lockfile\s*=\s*true", backend)
    assert re.search(r"encrypt\s*=\s*true", backend)
    assert "dynamodb_table" not in backend


@pytest.mark.parametrize("root", terraform_roots(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_r11_requires_terraform_1_10(root: Path) -> None:
    text = "\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.tf"))
    assert re.search(r'required_version\s*=\s*">=\s*1\.1\d', text)
    assert (root / ".terraform.lock.hcl").is_file(), "commit the provider lock file"


def test_r11_no_dynamodb_lock_table() -> None:
    for path in TF_FILES:
        text = path.read_text(encoding="utf-8")
        for backend in hcl_blocks(text, r"backend\s+\"\w+\"\s*\{"):
            assert "dynamodb_table" not in backend, path
        assert not re.search(r'"aws_dynamodb_table"\s+"\w*lock', text), path


@pytest.mark.parametrize("path", TF_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_r11_every_aws_provider_tags_project_and_env(path: Path) -> None:
    for provider in hcl_blocks(path.read_text(encoding="utf-8"), r'provider\s+"aws"\s*\{'):
        (tags,) = hcl_blocks(provider, r"default_tags\s*\{")
        assert re.search(r'project\s*=\s*"risk-trainer"', tags)
        assert re.search(r"env\s*=", tags)
