"""HTTP API: configuration and prompts of the activities."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import project_brevia
from fastapi.testclient import TestClient
from httpx2 import Response
from memory_store import MemoryStore
from pydantic import SecretStr
from summary_example import (
    PROMPT,
    SummaryConfig,
    SummaryRequest,
    SummaryResult,
    summarize,
)

from brevia import AccessPolicy, create_token
from brevia.access.auth import AuthSettings
from brevia.api import create_app

pytestmark = pytest.mark.unit

SECRET = "s" * 32
ACTIVITY = "test.custom"
CUSTOM_PROMPT = "Write a summary in {language}, in three sentences."


def headers(user: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(user, 5, SECRET)}"}


ADMIN = headers("admin")
APP = headers("bedita")


@pytest.fixture
def client(tmp_path: Path, store: MemoryStore) -> Iterator[TestClient]:
    app = project_brevia(
        tmp_path, store, access=AccessPolicy(admins=frozenset({"admin"}))
    )
    app.register_activity(
        name=ACTIVITY,
        version="1",
        function=summarize,
        input_type=SummaryRequest,
        output_type=SummaryResult,
        config_type=SummaryConfig,
        prompts={"summary": "prompts/summary.md"},
        customizable=["max_output_tokens", "language"],
    )
    settings = AuthSettings(
        tokens_secret=SecretStr(SECRET),
        tokens_users="",
        auth_disabled=False,
        status_token=None,
    )
    with TestClient(create_app(app, settings)) as test_client:
        yield test_client


def assert_error(response: Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body: dict[str, Any] = response.json()
    assert body["code"] == code
    return body


# ---------- configuration ----------


def test_configurations_are_read_by_every_caller(client: TestClient) -> None:
    listed = client.get("/configurations", headers=APP).json()
    assert [state["activity"] for state in listed] == ["document.summarize", ACTIVITY]
    state = client.get(f"/configurations/{ACTIVITY}", headers=APP).json()
    assert state["version"] == 0
    assert state["customization"] == {}
    assert state["effective"]["max_output_tokens"] == 1200
    assert state["customizable"] == ["language", "max_output_tokens"]
    assert "properties" in state["config_schema"]
    assert_error(client.get("/configurations/missing", headers=APP), 404, "not_found")
    assert_error(client.get("/configurations"), 401, "unauthorized")


def test_an_administrator_customises_and_resets_the_configuration(
    client: TestClient,
) -> None:
    change = {"values": {"max_output_tokens": 1800}, "expected_version": 0}
    response = client.patch(f"/configurations/{ACTIVITY}", json=change, headers=ADMIN)
    assert response.status_code == 200
    state = response.json()
    assert state["customization"] == {"max_output_tokens": 1800}
    assert state["effective"]["max_output_tokens"] == 1800
    assert state["version"] == 1
    assert state["updated_by"] == "admin"

    reset = {"fields": ["max_output_tokens"], "expected_version": 1}
    response = client.post(
        f"/configurations/{ACTIVITY}/reset", json=reset, headers=ADMIN
    )
    state = response.json()
    assert state["customization"] == {}
    assert state["effective"]["max_output_tokens"] == 1200
    assert state["version"] == 2


def test_a_stale_version_is_refused_with_412(client: TestClient) -> None:
    url = f"/configurations/{ACTIVITY}"
    client.patch(url, json={"values": {"language": "en"}}, headers=ADMIN)
    stale = {"values": {"language": "fr"}, "expected_version": 0}
    assert_error(client.patch(url, json=stale, headers=ADMIN), 412, "version_conflict")
    assert client.get(url, headers=ADMIN).json()["customization"] == {"language": "en"}


def test_only_administrators_change_the_configuration(client: TestClient) -> None:
    url = f"/configurations/{ACTIVITY}"
    change = {"values": {"language": "en"}}
    assert_error(client.patch(url, json=change, headers=APP), 403, "forbidden")
    assert_error(client.post(f"{url}/reset", json={}, headers=APP), 403, "forbidden")


def test_invalid_changes_keep_their_code(client: TestClient) -> None:
    url = f"/configurations/{ACTIVITY}"
    not_customizable = {"values": {"model": "openai:other"}}
    response = client.patch(url, json=not_customizable, headers=ADMIN)
    assert_error(response, 422, "invalid_input")
    extra = {"values": {"language": "en"}, "author": "someone else"}
    assert_error(client.patch(url, json=extra, headers=ADMIN), 422, "invalid_input")


def test_the_author_is_the_end_user_of_the_caller(
    tmp_path: Path, store: MemoryStore
) -> None:
    app = project_brevia(tmp_path, store, access=AccessPolicy(shared=True))
    settings = AuthSettings(
        tokens_secret=None, tokens_users="", auth_disabled=True, status_token=None
    )
    with TestClient(create_app(app, settings)) as anonymous:
        # Authentication disabled: every caller is "anonymous", with no end user.
        prompt = anonymous.put(
            "/prompts/document.summarize/summary", json={"text": CUSTOM_PROMPT}
        )
        assert prompt.json()["updated_by"] == "anonymous"


# ---------- prompts ----------


def test_prompts_are_listed_and_read(client: TestClient) -> None:
    listed = client.get("/prompts", headers=APP).json()
    assert [(p["activity"], p["name"]) for p in listed] == [
        ("document.summarize", "summary"),
        (ACTIVITY, "summary"),
    ]
    state = client.get(f"/prompts/{ACTIVITY}/summary", headers=APP).json()
    assert state["file_text"] == PROMPT
    assert state["effective"] == PROMPT
    assert state["customization"] is None
    assert state["variables"] == ["language"]
    missing = client.get(f"/prompts/{ACTIVITY}/missing", headers=APP)
    assert_error(missing, 404, "not_found")


def test_a_prompt_is_customised_reset_and_restored_from_its_history(
    client: TestClient,
) -> None:
    url = f"/prompts/{ACTIVITY}/summary"
    change = {"text": CUSTOM_PROMPT, "expected_version": 0}
    state = client.put(url, json=change, headers=ADMIN).json()
    assert (state["effective"], state["version"]) == (CUSTOM_PROMPT, 1)

    reset = client.post(f"{url}/reset", json={"expected_version": 1}, headers=ADMIN)
    assert (reset.json()["effective"], reset.json()["version"]) == (PROMPT, 2)

    revisions = client.get(f"{url}/revisions", headers=APP).json()
    assert [(r["version"], r["operation"]) for r in revisions] == [
        (2, "reset"),
        (1, "customize"),
    ]
    # Restoring a revision is saving its text again.
    restored = client.put(url, json={"text": revisions[1]["text"]}, headers=ADMIN)
    assert (restored.json()["effective"], restored.json()["version"]) == (
        CUSTOM_PROMPT,
        3,
    )


def test_prompt_changes_are_checked(client: TestClient) -> None:
    url = f"/prompts/{ACTIVITY}/summary"
    wrong = {"text": "Summarise in {lingua}."}
    assert_error(client.put(url, json=wrong, headers=ADMIN), 422, "invalid_input")
    assert_error(
        client.put(url, json={"text": CUSTOM_PROMPT}, headers=APP), 403, "forbidden"
    )
    client.put(url, json={"text": CUSTOM_PROMPT}, headers=ADMIN)
    stale = client.post(f"{url}/reset", json={"expected_version": 0}, headers=ADMIN)
    assert_error(stale, 412, "version_conflict")


def test_the_author_is_the_end_user_of_the_body(client: TestClient) -> None:
    prompt = f"/prompts/{ACTIVITY}/summary"
    configuration = f"/configurations/{ACTIVITY}"
    user = {"end_user": "user-42"}
    changes = [
        client.put(prompt, json={"text": CUSTOM_PROMPT} | user, headers=ADMIN),
        client.post(f"{prompt}/reset", json=user, headers=ADMIN),
        client.patch(
            configuration, json={"values": {"language": "en"}} | user, headers=ADMIN
        ),
        client.post(f"{configuration}/reset", json=user, headers=ADMIN),
    ]
    assert [change.json()["updated_by"] for change in changes] == ["user-42"] * 4
    revisions = client.get(f"{prompt}/revisions", headers=APP).json()
    assert [revision["author"] for revision in revisions] == ["user-42"] * 2
    # Without an end user, the caller.
    response = client.patch(
        configuration, json={"values": {"language": "fr"}}, headers=ADMIN
    )
    assert response.json()["updated_by"] == "admin"


@pytest.mark.parametrize("user", [" ", "u" * 201, "user\x00"])
def test_an_invalid_end_user_is_refused(client: TestClient, user: str) -> None:
    url = f"/prompts/{ACTIVITY}/summary"
    response = client.put(
        url, json={"text": CUSTOM_PROMPT, "end_user": user}, headers=ADMIN
    )
    body = assert_error(response, 422, "invalid_input")
    assert body["details"] == {"field": "end_user"}
    assert "u" * 201 not in response.text  # the value is not returned
    assert client.get(url, headers=APP).json()["version"] == 0


def test_the_end_user_is_documented_on_every_change(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in (
        "RunRequest",
        "ConfigurationChange",
        "ConfigurationReset",
        "PromptChange",
        "PromptReset",
    ):
        field = schemas[name]["properties"]["end_user"]
        assert "never a name or an email" in field["description"]
