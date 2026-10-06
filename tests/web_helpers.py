"""Helpers for web tests: an app built from the frozen rt-001 fixture and a form filler."""

import copy
import re
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from risk_trainer.config import Settings
from risk_trainer.domain.models import Scenario
from risk_trainer.domain.rules import parse_scenario
from risk_trainer.storage.attempts import AttemptStore
from risk_trainer.storage.memory import MemoryAttemptStore
from risk_trainer.storage.rate_limits import RateLimiter
from risk_trainer.web.app import create_app
from tests.helpers import RT001_DATA, approved

RT001_ID = "rt-001-five-findings"
SECRET = "test-session-secret-" + "x" * 32

# rt-001's expert answers, with the correct approver for the accepted finding.
EXPERT_ANSWERS = {
    "F1.treatment": "mitigate_remediate",
    "F2.treatment": "mitigate_compensate",
    "F3.treatment": "transfer",
    "F4.treatment": "mitigate_remediate",
    "F5.treatment": "accept",
    "F5.approver": "business_risk_owner",
    "F5.rationale": "Low impact and the owner understands it.",
}


def scenario_from(data: dict[str, Any]) -> Scenario:
    return parse_scenario(data)


def rt001(status: str = "approved", **changes: Any) -> Scenario:
    data = approved(RT001_DATA) if status == "approved" else copy.deepcopy(RT001_DATA)
    data["status"] = status
    data.update(changes)
    if status == "draft":
        data["reviewed_by"] = None
        data["reviewed_on"] = None
    return parse_scenario(data)


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "storage_backend": "memory",
        "session_secret": SECRET,
        "content_dir": Path("does-not-exist"),
    }
    values.update(overrides)
    return Settings(**values)


def client(
    scenarios: list[Scenario] | None = None,
    store: AttemptStore | None = None,
    *,
    preview: bool = False,
    rate_limiter: RateLimiter | None = None,
    **setting_overrides: Any,
) -> TestClient:
    app = create_app(
        settings(**setting_overrides),
        store if store is not None else MemoryAttemptStore(),
        scenarios if scenarios is not None else [rt001()],
        preview=preview,
        rate_limiter=rate_limiter,
    )
    return TestClient(app, base_url="https://testserver", raise_server_exceptions=False)


def form_fields(html: str) -> dict[str, str]:
    """The hidden csrf_token and submit_id from a rendered exercise form."""
    fields = {}
    for name in ("csrf_token", "submit_id"):
        match = re.search(rf'name="{name}" value="([^"]+)"', html)
        assert match, f"no {name} in form"
        fields[name] = match.group(1)
    return fields


def submit(
    test_client: TestClient,
    answers: dict[str, str] | None = None,
    scenario_id: str = RT001_ID,
    **extra: str,
) -> Any:
    page = test_client.get(f"/s/{scenario_id}")
    data = {**form_fields(page.text), **(EXPERT_ANSWERS if answers is None else answers), **extra}
    return test_client.post(f"/s/{scenario_id}", data=data)
