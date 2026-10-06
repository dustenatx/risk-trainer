"""R7 — the submit endpoint: 422 for rule breaks, 413 for big bodies, CSRF on POST."""

from collections.abc import Iterator

from tests.web_helpers import EXPERT_ANSWERS, RT001_ID, client, form_fields, submit


def test_r7_rule_break_returns_422_with_readable_message() -> None:
    response = submit(client(), {**EXPERT_ANSWERS, "F2.treatment": "mitigate_remediate"})
    assert response.status_code == 422
    assert "the team has capacity for 2" in response.text
    assert 'role="alert"' in response.text


def test_r7_422_keeps_learner_answers_in_form() -> None:
    answers = {**EXPERT_ANSWERS, "F1.rationale": "keep me", "F2.treatment": "<bad>"}
    response = submit(client(), answers)
    assert response.status_code == 422
    assert ">keep me</textarea>" in response.text
    assert 'value="mitigate_remediate" checked' in response.text


def test_r7_missing_submit_id_returns_422() -> None:
    test_client = client()
    page = test_client.get(f"/s/{RT001_ID}")
    data = {"csrf_token": form_fields(page.text)["csrf_token"], **EXPERT_ANSWERS}
    assert test_client.post(f"/s/{RT001_ID}", data=data).status_code == 422


def test_r7_post_without_csrf_is_403() -> None:
    test_client = client()
    page = test_client.get(f"/s/{RT001_ID}")
    data = {"submit_id": form_fields(page.text)["submit_id"], **EXPERT_ANSWERS}
    assert test_client.post(f"/s/{RT001_ID}", data=data).status_code == 403


def test_r7_post_with_wrong_csrf_is_403() -> None:
    assert submit(client(), {**EXPERT_ANSWERS, "csrf_token": "forged"}).status_code == 403


def test_r7_post_from_new_session_is_403() -> None:
    first = client()
    fields = form_fields(first.get(f"/s/{RT001_ID}").text)
    response = client().post(f"/s/{RT001_ID}", data={**fields, **EXPERT_ANSWERS})
    assert response.status_code == 403


def test_r7_body_over_32kb_is_413() -> None:
    response = client().post(
        f"/s/{RT001_ID}",
        content=b"a=" + b"x" * (32 * 1024),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"


def test_r7_streamed_body_over_32kb_is_413() -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(40):
            yield b"x" * 1024

    response = client().post(
        f"/s/{RT001_ID}",
        content=chunks(),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 413


def test_r7_body_at_limit_is_parsed() -> None:
    test_client = client()
    fields = form_fields(test_client.get(f"/s/{RT001_ID}").text)
    data = {**fields, **EXPERT_ANSWERS, "note": "n" * 1200}
    assert test_client.post(f"/s/{RT001_ID}", data=data).status_code == 200


def test_r7_unknown_scenario_is_404() -> None:
    assert client().get("/s/rt-999-missing").status_code == 404
