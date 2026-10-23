"""R14 — CI/CD: OIDC only, plan on merge to main, apply gated by the protected prod environment."""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.helpers import REPO_ROOT

WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
DEPLOY = WORKFLOWS / "deploy.yml"
TERRAFORM_JOBS = ("plan", "apply")


def load(path: Path) -> dict[Any, Any]:
    data: dict[Any, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = job["steps"]
    return result


@pytest.mark.parametrize("path", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
def test_r14_every_third_party_action_pinned_to_a_sha(path: Path) -> None:
    for uses in re.findall(r"uses:\s*([^\s#]+)", path.read_text(encoding="utf-8")):
        if uses.startswith("./"):
            continue
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", uses), uses


def test_r14_deploy_triggers_on_main_only() -> None:
    triggers = load(DEPLOY)[True]  # PyYAML reads the bare `on` key as True
    assert triggers["push"] == {"branches": ["main"]}
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert "pull_request" not in DEPLOY.read_text(encoding="utf-8")


def test_r14_oidc_only_no_long_lived_keys() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    for forbidden in ("aws-access-key-id", "aws-secret-access-key", "AWS_ACCESS_KEY_ID"):
        assert forbidden not in text
    workflow = load(DEPLOY)
    assert workflow["permissions"] == {"contents": "read"}
    for name in TERRAFORM_JOBS:
        job = workflow["jobs"][name]
        assert job["permissions"] == {"contents": "read", "id-token": "write"}
        creds = [s for s in steps(job) if "configure-aws-credentials" in s.get("uses", "")]
        assert len(creds) == 1
        assert creds[0]["with"]["role-to-assume"].startswith("${{ vars.")


def test_r14_plan_job_has_no_environment_and_uses_the_plan_role() -> None:
    plan = load(DEPLOY)["jobs"]["plan"]
    # The plan role trusts only refs/heads/main; an environment would change the OIDC subject.
    assert "environment" not in plan
    (creds,) = [s for s in steps(plan) if "configure-aws-credentials" in s.get("uses", "")]
    assert creds["with"]["role-to-assume"] == "${{ vars.AWS_PLAN_ROLE_ARN }}"


def test_r14_apply_waits_for_the_protected_prod_environment() -> None:
    apply = load(DEPLOY)["jobs"]["apply"]
    assert apply["environment"] == "prod"
    assert apply["needs"] == "plan"
    (creds,) = [s for s in steps(apply) if "configure-aws-credentials" in s.get("uses", "")]
    assert creds["with"]["role-to-assume"] == "${{ vars.AWS_DEPLOY_ROLE_ARN }}"
    runs = " ".join(s.get("run", "") for s in steps(apply))
    assert "apply -input=false" in runs and "tfplan" in runs


def test_r14_both_jobs_build_the_package_before_terraform() -> None:
    for name in TERRAFORM_JOBS:
        job = load(DEPLOY)["jobs"][name]
        runs = [s.get("run", "") for s in steps(job)]
        package = next(i for i, r in enumerate(runs) if r == "make package")
        terraform = next(i for i, r in enumerate(runs) if "terraform" in r)
        assert package < terraform


def test_r14_deploy_has_exactly_plan_apply_and_smoke() -> None:
    assert set(load(DEPLOY)["jobs"]) == {*TERRAFORM_JOBS, "smoke"}


def test_r14_smoke_runs_after_apply_read_only() -> None:
    smoke = load(DEPLOY)["jobs"]["smoke"]
    assert smoke["needs"] == "apply"
    assert smoke["permissions"] == {"contents": "read"}
    assert "environment" not in smoke
    assert smoke["runs-on"] == "ubuntu-24.04"
    assert smoke["timeout-minutes"] <= 15
    assert smoke["env"] == {"SMOKE_BASE_URL": "${{ vars.SMOKE_BASE_URL }}"}
    assert "secrets." not in yaml.safe_dump(smoke)
    assert not [s for s in steps(smoke) if "configure-aws-credentials" in s.get("uses", "")]
    runs = [s.get("run", "") for s in steps(smoke)]
    guard = next(i for i, r in enumerate(runs) if '-z "$SMOKE_BASE_URL"' in r)
    assert guard < runs.index("make smoke")


def test_r14_smoke_checkout_includes_static_files() -> None:
    smoke = load(DEPLOY)["jobs"]["smoke"]
    (checkout,) = [s for s in steps(smoke) if "checkout" in s.get("uses", "")]
    assert set(checkout.get("with", {})) <= {"persist-credentials"}


def locked_playwright_version() -> str:
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text(encoding="utf-8"))
    (version,) = [p["version"] for p in lock["package"] if p["name"] == "playwright"]
    return str(version)


def test_r14_e2e_runs_in_playwright_image_matching_lock() -> None:
    # The image ships the browsers for one Playwright release; a mismatch fails at launch.
    container = load(CI)["jobs"]["e2e"]["container"]
    image = re.escape(f"mcr.microsoft.com/playwright/python:v{locked_playwright_version()}-noble")
    assert re.fullmatch(image + r"@sha256:[0-9a-f]{64}", container["image"]), container["image"]
    assert container["options"] == "--user 1001"


def test_r14_e2e_installs_no_browsers_and_stays_read_only() -> None:
    workflow = load(CI)
    e2e = workflow["jobs"]["e2e"]
    assert e2e["runs-on"] == "ubuntu-24.04"
    assert e2e["timeout-minutes"] <= 10
    assert e2e.get("permissions", workflow["permissions"]) == {"contents": "read"}
    for step in steps(e2e):
        run = step.get("run", "")
        assert "playwright install" not in run and "apt-get" not in run, step.get("name")
        assert "actions/cache" not in step.get("uses", ""), step.get("uses")


def test_r14_e2e_command_matches_makefile_recipe() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    match = re.search(r"^e2e:\n((?:\t.*\n)+)", makefile, re.MULTILINE)
    assert match, "Makefile has no e2e recipe"
    recipe = "\n".join(line.removeprefix("\t") for line in match.group(1).splitlines())
    (test_step,) = [s for s in steps(load(CI)["jobs"]["e2e"]) if "pytest" in s.get("run", "")]
    assert test_step["run"].strip() == recipe


def test_r14_no_template_expressions_inside_run_scripts() -> None:
    for job in load(DEPLOY)["jobs"].values():
        for step in steps(job):
            assert "${{" not in step.get("run", ""), step.get("name")
